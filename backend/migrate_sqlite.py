"""Import one local event SQLite snapshot into an empty PostgreSQL event database."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from dotenv import load_dotenv

if __name__=='__main__':
    load_dotenv(Path(__file__).parent / '.env')
import logger_db
from timeglitch_engine import TimeglitchSession

TABLE_COLUMNS = {
    'event_sessions':['batch_id','name','started_at','ended_at'],
    'teams': ['team_id','team_name','school_name','participants','registered_at','token_hash','status','batch_id'],
    'game_sessions': ['session_id','team_id','state','pending_token','pending_until','last_prompt_at','quality_override','quality_reason','quality_reviewed_at'],
    'quality_audit': ['id','session_id','score','reason','reviewed_at'],
    'admin_sessions': ['token_hash','expires_at'],
    'login_limits': ['address','count','window_start'],
    'provider_budget_state': ['scope','cooldown_until'],
    'provider_reservations': ['id','scope','started_at','tokens','team_id','active_until'],
    'provider_waiters': ['scope','team_id','waiting_since','expires_at'],
    'timeline_attempts':['id','session_id','team_id','batch_id','submitted_at','attempt','placed_ids','slot_results','correct','score'],
    'word_answers':['id','session_id','team_id','batch_id','submitted_at','word_index','answer','correct','outcome'],
    'failed_requests':['id','session_id','team_id','batch_id','submitted_at','prompt','target','error','reason','retry_seconds','details'],
}
REQUIRED_TABLES = {'event','teams','game_sessions','quality_audit'}


def read_snapshot(source):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError('The SQLite source does not exist.')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        with closing(sqlite3.connect(':memory:')) as snapshot:
            original.backup(snapshot)
            snapshot.row_factory = sqlite3.Row
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or snapshot.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('The source database failed integrity checks.')
            tables = {row[0] for row in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED_TABLES <= tables:
                raise ValueError('The source is not a current event database. The old password-game database is unsupported.')
            event_columns={row['name'] for row in snapshot.execute('PRAGMA table_info(event)')}
            active_column='active_batch_id' if 'active_batch_id' in event_columns else "'morning' AS active_batch_id"
            events = snapshot.execute('SELECT id,started_at,ended_at,' + active_column + ' FROM event').fetchall()
            if len(events) != 1 or events[0]['id'] != 1:
                raise ValueError('The source needs one valid event record.')
            rows = {}
            for table, columns in TABLE_COLUMNS.items():
                existing_columns={row['name'] for row in snapshot.execute('PRAGMA table_info(' + table + ')')} if table in tables else set()
                select=["'morning' AS batch_id" if column=='batch_id' and column not in existing_columns else column for column in columns]
                rows[table] = [dict(row) for row in snapshot.execute('SELECT ' + ','.join(select) + ' FROM ' + table)] if table in tables else []
            if not rows['event_sessions']:
                rows['event_sessions']=[{'batch_id':'morning','name':'Morning','started_at':events[0]['started_at'],'ended_at':events[0]['ended_at']},
                                        {'batch_id':'afternoon','name':'Afternoon','started_at':None,'ended_at':None}]
    teams = {row['team_id'] for row in rows['teams']}
    if len(rows['game_sessions']) != len(teams):
        raise ValueError('Every registered team needs exactly one saved game session.')
    for row in rows['game_sessions']:
        state = json.loads(row['state'])
        engine = TimeglitchSession.from_storage(state)
        if engine.team_id != row['team_id'] or engine.session_id != row['session_id'] or row['team_id'] not in teams:
            raise ValueError('A source session does not match its registered team.')
        if row['pending_token'] and row['pending_until'] > time.time():
            raise ValueError('A provider request is still pending. Stop the old server, wait 90 seconds, and retry.')
        row['pending_token'], row['pending_until'] = None, 0
    return dict(events[0]), rows


def migrate(source):
    if logger_db.storage_kind() != 'postgres':
        raise ValueError('Set DATABASE_URL to an empty PostgreSQL event database before migration.')
    event, rows = read_snapshot(source)
    logger_db.init_db()
    with logger_db.transaction() as conn:
        target_event = conn.execute('SELECT started_at,ended_at FROM event WHERE id=1').fetchone()
        if target_event['started_at'] is not None or target_event['ended_at'] is not None:
            raise ValueError('The PostgreSQL destination already contains an event. Nothing was imported.')
        for table in TABLE_COLUMNS:
            if table=='event_sessions':
                if any(row['started_at'] is not None or row['ended_at'] is not None for row in conn.execute('SELECT * FROM event_sessions')):
                    raise ValueError('The PostgreSQL destination already contains an event session. Nothing was imported.')
                continue
            if conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]:
                raise ValueError('The PostgreSQL destination is not empty. Nothing was imported.')
        for table, columns in TABLE_COLUMNS.items():
            sql = 'INSERT INTO ' + table + '(' + ','.join(columns) + ') VALUES(' + ','.join('?' for _ in columns) + ')'
            if table=='event_sessions':
                sql+=' ON CONFLICT(batch_id) DO UPDATE SET name=excluded.name,started_at=excluded.started_at,ended_at=excluded.ended_at'
            for row in rows[table]:
                conn.execute(sql, tuple(row[column] for column in columns))
            saved = [dict(row) for row in conn.execute('SELECT ' + ','.join(columns) + ' FROM ' + table)]
            # Compare every copied column without printing private tokens or state.
            key_columns = columns[:2] if table == 'provider_waiters' else columns[:1]
            canonical = lambda items: {tuple(item[column] for column in key_columns): item for item in items}
            if canonical(saved) != canonical(rows[table]):
                raise RuntimeError('Migration verification failed; the transaction was rolled back.')
        conn.execute('UPDATE event SET started_at=?,ended_at=?,active_batch_id=? WHERE id=1', (event['started_at'], event['ended_at'],event['active_batch_id']))
        for table in ('quality_audit','timeline_attempts','word_answers','failed_requests'):
            conn.execute("SELECT setval(pg_get_serial_sequence('"+table+"','id'), COALESCE((SELECT MAX(id) FROM "+table+"),1), EXISTS(SELECT 1 FROM "+table+"))")
    return {table: len(items) for table, items in rows.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='A current event SQLite database or consistent backup')
    args = parser.parse_args()
    try:
        counts = migrate(args.source)
    except Exception as error:
        # PostgreSQL exceptions may include connection or row data.
        if isinstance(error, ValueError):
            parser.exit(1, str(error) + '\n')
        parser.exit(1, f'Migration failed ({type(error).__name__}); destination writes were rolled back.\n')
    print('Imported and verified ' + ', '.join(f'{count} {table}' for table,count in counts.items()) + '.')
