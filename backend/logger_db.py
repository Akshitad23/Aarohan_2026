"""Bounded PostgreSQL connections in hosting, SQLite for local work and tests."""
import atexit
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout, TooManyRequests
except ImportError:
    psycopg = None

DB_PATH = Path(os.getenv('DATABASE_PATH') or str(Path(__file__).parent / 'data' / 'event.sqlite3'))
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
_pool = None
_pool_pid = None
_pool_url = None
_pool_lock = threading.Lock()
SCHEMA_LOCK = 26002601
# Bump this when a schema migration is added. Worker restarts must not run DDL
# against tables that other ready workers are reading.
SCHEMA_VERSION = 3
DATABASE_ERRORS = (sqlite3.OperationalError,)
if psycopg is not None:
    DATABASE_ERRORS += (psycopg.OperationalError, PoolClosed, PoolTimeout, TooManyRequests)


def storage_kind():
    return 'postgres' if DATABASE_URL else 'sqlite'


def require_persistent_host_storage():
    hosted = os.getenv('RENDER') == 'true' or os.getenv('RENDER_SERVICE_ID') or os.getenv('REQUIRE_DATABASE_URL', '').lower() == 'true'
    if hosted and not DATABASE_URL:
        raise RuntimeError('Render requires DATABASE_URL. Local SQLite storage is not persistent on the free service.')


class Row(dict):
    """Keep index access for scalar queries alongside named application columns."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.raw = cursor

    def fetchone(self):
        row = self.raw.fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(row) for row in self.raw.fetchall()]

    def __iter__(self):
        for row in self.raw:
            yield Row(row)

    @property
    def rowcount(self):
        return self.raw.rowcount


class Connection:
    def __init__(self, raw, pool=None):
        self.raw, self.pool = raw, pool
        self.postgres = pool is not None
        self.closed = False

    def execute(self, sql, parameters=None):
        # SQL is maintained in this repository; values stay in bound parameters.
        # No caller supplies SQL identifiers, operators or query fragments.
        if self.postgres:
            if parameters is not None:
                sql = sql.replace('%', '%%').replace('?', '%s')
            return Cursor(self.raw.execute(sql, parameters))
        return self.raw.execute(sql, parameters or ())

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.pool is None:
            self.raw.close()
        else:
            try:
                self.raw.rollback()
            finally:
                self.pool.putconn(self.raw)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.rollback() if kind else self.commit()
        finally:
            self.close()


def close_pool():
    global _pool, _pool_pid, _pool_url
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = _pool_pid = _pool_url = None


atexit.register(close_pool)


def postgres_pool():
    global _pool, _pool_pid, _pool_url
    if psycopg is None:
        raise RuntimeError('Install psycopg[binary] and psycopg_pool to use DATABASE_URL.')
    with _pool_lock:
        # Gunicorn workers must create their own pools after forking.
        if _pool is None or _pool_pid != os.getpid() or _pool_url != DATABASE_URL:
            if _pool is not None and _pool_pid == os.getpid():
                _pool.close()
            _pool = ConnectionPool(DATABASE_URL, min_size=0,
                max_size=max(1, min(8, int(os.getenv('DB_POOL_MAX', '4')))),
                timeout=20, max_waiting=64, max_idle=60, max_lifetime=300,
                kwargs={'row_factory':dict_row, 'connect_timeout':15, 'prepare_threshold':None},
                open=False, num_workers=1, name='aarohan')
            _pool.open()
            _pool_pid, _pool_url = os.getpid(), DATABASE_URL
        return _pool


def connect():
    require_persistent_host_storage()
    if DATABASE_URL:
        pool = postgres_pool()
        return Connection(pool.getconn(), pool)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(DB_PATH), timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute('PRAGMA foreign_keys=ON')
    raw.execute('PRAGMA busy_timeout=15000')
    return Connection(raw)


@contextmanager
def transaction():
    conn = connect()
    try:
        if conn.postgres:
            conn.execute('BEGIN')
            # Short event mutations and quota reservations serialize across workers.
            # Provider HTTP requests always happen after this transaction commits.
            conn.execute('SELECT id FROM event WHERE id=1 FOR UPDATE')
        else:
            conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        if conn.postgres:
            conn.execute('SELECT pg_advisory_xact_lock(?)', (SCHEMA_LOCK,))
            has_meta=conn.execute("SELECT to_regclass('schema_meta')").fetchone()[0] is not None
        else:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA foreign_keys=OFF')
            conn.execute('BEGIN IMMEDIATE')
            has_meta=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'").fetchone() is not None
        if has_meta:
            version=conn.execute('SELECT version FROM schema_meta WHERE id=1').fetchone()
            if version and version['version']>=SCHEMA_VERSION:
                return
        real = 'DOUBLE PRECISION' if conn.postgres else 'REAL'
        audit_id = 'BIGSERIAL PRIMARY KEY' if conn.postgres else 'INTEGER PRIMARY KEY AUTOINCREMENT'
        statements = [
            f'CREATE TABLE IF NOT EXISTS event(id INTEGER PRIMARY KEY CHECK(id=1),started_at {real},ended_at {real})',
            'INSERT INTO event(id) VALUES(1) ON CONFLICT(id) DO NOTHING',
            f'CREATE TABLE IF NOT EXISTS event_sessions(batch_id TEXT PRIMARY KEY,name TEXT NOT NULL,started_at {real},ended_at {real})',
            "INSERT INTO event_sessions(batch_id,name,started_at,ended_at) SELECT 'morning','Morning',started_at,ended_at FROM event WHERE id=1 ON CONFLICT(batch_id) DO NOTHING",
            "INSERT INTO event_sessions(batch_id,name) VALUES('afternoon','Afternoon') ON CONFLICT(batch_id) DO NOTHING",
            f'''CREATE TABLE IF NOT EXISTS teams(team_id TEXT PRIMARY KEY,team_name TEXT NOT NULL,
                school_name TEXT NOT NULL,participants TEXT NOT NULL,registered_at {real} NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'Confirmed')''',
            f'''CREATE TABLE IF NOT EXISTS game_sessions(session_id TEXT PRIMARY KEY,team_id TEXT NOT NULL UNIQUE REFERENCES teams(team_id),
                state TEXT NOT NULL,pending_token TEXT,pending_until {real} NOT NULL DEFAULT 0,last_prompt_at {real} NOT NULL DEFAULT 0,
                quality_override {real},quality_reason TEXT,quality_reviewed_at {real})''',
            f'''CREATE TABLE IF NOT EXISTS quality_audit(id {audit_id},session_id TEXT NOT NULL REFERENCES game_sessions(session_id),
                score {real} NOT NULL,reason TEXT NOT NULL,reviewed_at {real} NOT NULL)''',
            f'CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at {real} NOT NULL)',
            f'CREATE TABLE IF NOT EXISTS login_limits(address TEXT PRIMARY KEY,count INTEGER NOT NULL,window_start {real} NOT NULL)',
            f'CREATE TABLE IF NOT EXISTS provider_budget_state(scope TEXT PRIMARY KEY,cooldown_until {real} NOT NULL DEFAULT 0)',
            f'''CREATE TABLE IF NOT EXISTS provider_reservations(id TEXT PRIMARY KEY,scope TEXT NOT NULL,started_at {real} NOT NULL,
                tokens INTEGER NOT NULL,team_id TEXT NOT NULL,active_until {real} NOT NULL DEFAULT 0)''',
            'CREATE INDEX IF NOT EXISTS provider_reservations_window ON provider_reservations(scope,started_at)',
            f'''CREATE TABLE IF NOT EXISTS provider_waiters(scope TEXT NOT NULL,team_id TEXT NOT NULL,
                waiting_since {real} NOT NULL,expires_at {real} NOT NULL,PRIMARY KEY(scope,team_id))''',
            f'''CREATE TABLE IF NOT EXISTS timeline_attempts(id {audit_id},session_id TEXT NOT NULL REFERENCES game_sessions(session_id),
                team_id TEXT NOT NULL,batch_id TEXT NOT NULL,submitted_at {real} NOT NULL,attempt INTEGER NOT NULL,
                placed_ids TEXT NOT NULL,slot_results TEXT NOT NULL,correct INTEGER NOT NULL,score INTEGER NOT NULL)''',
            f'''CREATE TABLE IF NOT EXISTS word_answers(id {audit_id},session_id TEXT NOT NULL REFERENCES game_sessions(session_id),
                team_id TEXT NOT NULL,batch_id TEXT NOT NULL,submitted_at {real} NOT NULL,word_index TEXT NOT NULL,
                answer TEXT NOT NULL,correct INTEGER,outcome TEXT NOT NULL)''',
            f'''CREATE TABLE IF NOT EXISTS failed_requests(id {audit_id},session_id TEXT NOT NULL REFERENCES game_sessions(session_id),
                team_id TEXT NOT NULL,batch_id TEXT NOT NULL,submitted_at {real} NOT NULL,prompt TEXT NOT NULL,
                target TEXT,error TEXT NOT NULL,reason TEXT NOT NULL,retry_seconds INTEGER NOT NULL,details TEXT NOT NULL)''',
            f'''CREATE TABLE IF NOT EXISTS prompt_requests(request_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES game_sessions(session_id),
                team_id TEXT NOT NULL,batch_id TEXT NOT NULL,submitted_at {real} NOT NULL,prompt TEXT NOT NULL,target TEXT,
                status TEXT NOT NULL,lease_until {real} NOT NULL,completed_at {real},details TEXT NOT NULL)''',
            'CREATE INDEX IF NOT EXISTS prompt_requests_session ON prompt_requests(session_id,submitted_at)',
        ]
        for statement in statements:
            conn.execute(statement)
        if conn.postgres:
            conn.execute("ALTER TABLE event ADD COLUMN IF NOT EXISTS active_batch_id TEXT NOT NULL DEFAULT 'morning'")
            conn.execute("ALTER TABLE teams ADD COLUMN IF NOT EXISTS batch_id TEXT NOT NULL DEFAULT 'morning'")
        else:
            for table, column, definition in (('event','active_batch_id',"TEXT NOT NULL DEFAULT 'morning'"), ('teams','batch_id',"TEXT NOT NULL DEFAULT 'morning'")):
                if column not in [row['name'] for row in conn.execute('PRAGMA table_info(' + table + ')')]:
                    conn.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + column + ' ' + definition)
            # Early local versions had an inline UNIQUE team-name constraint.
            # Rebuild only that table, retaining IDs and all referencing rows.
            inline_unique = False
            for index in conn.execute('PRAGMA index_list(teams)').fetchall():
                if index['origin'] == 'u' and [row['name'] for row in conn.execute('PRAGMA index_info(' + index['name'] + ')')] == ['team_name']:
                    inline_unique = True
            if inline_unique:
                conn.execute(f'''CREATE TABLE teams_batch_migration(team_id TEXT PRIMARY KEY,team_name TEXT NOT NULL,
                    school_name TEXT NOT NULL,participants TEXT NOT NULL,registered_at {real} NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'Confirmed',batch_id TEXT NOT NULL DEFAULT 'morning')''')
                conn.execute('INSERT INTO teams_batch_migration SELECT team_id,team_name,school_name,participants,registered_at,token_hash,status,batch_id FROM teams')
                conn.execute('DROP TABLE teams')
                conn.execute('ALTER TABLE teams_batch_migration RENAME TO teams')
        conn.execute('DROP INDEX IF EXISTS teams_name_ci')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS teams_batch_name_ci ON teams(batch_id,LOWER(team_name))')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_meta(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL)')
        conn.execute('INSERT INTO schema_meta(id,version) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version',(SCHEMA_VERSION,))
