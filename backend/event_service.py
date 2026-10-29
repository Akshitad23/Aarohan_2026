"""Persistent event operations. Provider requests run outside SQLite transactions."""
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from logger_db import connect, transaction
from timeglitch_engine import ROUND2_SECONDS, TimeglitchSession

class EventError(Exception):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status = status
        self.details = details or {}

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def valid_target(value):
    return (type(value) is int and value in (1, 2)) or (isinstance(value, str) and value in ('one','two','word1','word2'))

def event_state(conn, batch_id=None):
    active = conn.execute('SELECT active_batch_id FROM event WHERE id=1').fetchone()[0]
    row = conn.execute('SELECT * FROM event_sessions WHERE batch_id=?', (batch_id or active,)).fetchone()
    if not row:
        raise EventError('Event session not found.', 404)
    return {'batch_id':row['batch_id'], 'name':row['name'], 'active_batch_id':active,
            'status': 'ended' if row['ended_at'] else 'running' if row['started_at'] else 'waiting',
            'started_at': row['started_at'], 'ended_at': row['ended_at']}

def list_batches(conn):
    return [event_state(conn, row['batch_id']) for row in conn.execute("SELECT batch_id FROM event_sessions ORDER BY CASE WHEN batch_id='morning' THEN 0 ELSE 1 END,batch_id")]

def team_dict(row, private=False):
    result = {'team_id': row['team_id'], 'team_name': row['team_name'], 'school_name': row['school_name'],
              'batch_id':row['batch_id'],
              'status': row['status'], 'team_size': len(json.loads(row['participants'])),
              'registered_at': datetime.fromtimestamp(row['registered_at'], timezone.utc).isoformat()}
    if private:
        result['participants'] = json.loads(row['participants'])
    return result

def register(data):
    name = str(data.get('teamName', data.get('team_name', ''))).strip()
    school = str(data.get('schoolName', data.get('school_name', ''))).strip()
    members = data.get('participants')
    if not name or len(name) > 80 or not school or len(school) > 150:
        raise EventError('Enter a team name up to 80 characters and a school name up to 150 characters.')
    if not isinstance(members, list) or not 1 <= len(members) <= 6:
        raise EventError('A team must have 1 to 6 participants.')
    clean = []
    for member in members:
        if not isinstance(member, dict):
            raise EventError('Invalid participant details.')
        member_name = str(member.get('name', '')).strip()
        grade = str(member.get('grade', '')).strip()
        if not member_name or len(member_name) > 100 or not grade or len(grade) > 30:
            raise EventError("Enter each participant's name and grade.")
        clean.append({'name': member_name, 'grade': grade})
    token = secrets.token_urlsafe(32)
    team_id = 'AAR-' + secrets.token_hex(4).upper()
    with transaction() as conn:
        event = event_state(conn)
        batch_id = event['batch_id']
        if data.get('batch_id') and data['batch_id'] != batch_id:
            raise EventError('Registration has moved to another event session. Refresh the registration page.', 409)
        if event['status'] != 'waiting':
            raise EventError('Registration has closed because the event has started.', 409)
        if conn.execute('SELECT 1 FROM teams WHERE batch_id=? AND LOWER(team_name)=LOWER(?)', (batch_id,name)).fetchone():
            raise EventError('That team name is already registered. Resume with your team token.', 409)
        conn.execute('INSERT INTO teams(team_id,team_name,school_name,participants,registered_at,token_hash,batch_id) VALUES(?,?,?,?,?,?,?)',
                     (team_id, name, school, json.dumps(clean), time.time(), digest(token),batch_id))
        engine = TimeglitchSession(team_id, name)
        conn.execute('INSERT INTO game_sessions(session_id,team_id,state) VALUES(?,?,?)',
                     (engine.session_id, team_id, json.dumps(engine.to_storage())))
        row = conn.execute('SELECT * FROM teams WHERE team_id=?', (team_id,)).fetchone()
        return {'success': True, 'team': team_dict(row, True), 'team_token': token}

def authorized_team(conn, token):
    row = conn.execute('SELECT * FROM teams WHERE token_hash=?', (digest(token),)).fetchone()
    if not row:
        raise EventError('Your team token is missing or invalid. Ask an organizer to recover access.', 401)
    return row

def load(conn, team, history_after=None, include_history=True):
    if conn.postgres and (history_after is not None or not include_history):
        # Project in PostgreSQL so repeated polls do not transfer old transcripts
        # from Neon to Render. Full context remains available for provider calls.
        row = conn.execute('''SELECT session_id,team_id,(state::jsonb - 'prompt_history')::text AS state,
            pending_token,pending_until,last_prompt_at,quality_override,quality_reason,quality_reviewed_at
            FROM game_sessions WHERE team_id=?''', (team['team_id'],)).fetchone()
        data = json.loads(row['state'])
        data['prompt_history'] = []
        if history_after is not None and include_history:
            history = conn.execute('''SELECT item.value::text AS payload FROM game_sessions,
                LATERAL jsonb_array_elements(state::jsonb->'prompt_history') AS item(value)
                WHERE team_id=? AND (item.value->>'turn')::integer>? ORDER BY (item.value->>'turn')::integer''',
                (team['team_id'], history_after)).fetchall()
            data['prompt_history'] = [json.loads(turn['payload']) for turn in history]
    else:
        row = conn.execute('SELECT * FROM game_sessions WHERE team_id=?', (team['team_id'],)).fetchone()
        data = json.loads(row['state'])
        if not include_history:
            data['prompt_history'] = []
    return row, TimeglitchSession.from_storage(data)

def refresh(engine, event):
    if event['started_at']:
        engine.start_time = datetime.fromtimestamp(event['started_at'])
        engine.get_status()
    if event['ended_at'] and not engine.is_finished:
        if engine.round2_started:
            finish_session(engine, 'closed', datetime.fromtimestamp(event['ended_at']))
        else:
            engine.round1_status = 'closed'
            engine._finalize_scoring()

def finish_session(engine, status, finished_at=None):
    engine.round2_completed = True
    engine.round2_status = status
    engine.round2_timed_out = False
    engine.round2_finish_time = finished_at or datetime.now()
    engine._finalize_scoring()

def save(conn, engine):
    # Snapshot reads update clocks, but only gameplay changes need persistence.
    state = engine.to_storage()
    existing = conn.execute('SELECT state FROM game_sessions WHERE session_id=?', (engine.session_id,)).fetchone()
    previous = json.loads(existing['state'])
    stable, old_stable = dict(state), dict(previous)
    for key in ('round1_remaining_seconds','round1_elapsed_seconds','round2_remaining_seconds','round2_elapsed_seconds'):
        stable.pop(key, None)
        old_stable.pop(key, None)
    if stable != old_stable:
        conn.execute('UPDATE game_sessions SET state=? WHERE session_id=?', (json.dumps(state), engine.session_id))

def snapshot(engine, row, event):
    waiting = event['status'] == 'waiting'
    state = engine.get_status() if not waiting else {
        'session_id': engine.session_id, 'team_id': engine.team_id,
        'team_name': engine.team_name, 'round1': {}, 'round2': {},
        'total_score': 0, 'is_finished': False, 'prompt_history': []}
    phase = 'waiting' if waiting else 'finished' if engine.is_finished else 'round2' if engine.round2_started else 'round1'
    state.update(phase=phase, event=event, batch_id=event['batch_id'], server_time=time.time())
    if waiting:
        state.update(objective_score=0,final_score=None,quality_score=None,quality_status='pending',quality_reviewed=False)
        return state
    r1, r2 = state['round1'], state['round2']
    r1['attempts_left'] = max(0, 3 - engine.round1_attempts)
    r1['deadline'] = event['started_at'] + 600 if event['started_at'] else None
    if engine.round2_start_time:
        r2['deadline'] = engine.round2_start_time.timestamp() + ROUND2_SECONDS
    for index, word in enumerate(r2.get('words', []), 1):
        word['index'] = index
        key = f'word{index}'
        word['solved'] = engine.word_solved.get(key, False)
        word['score'] = engine.word_scores.get(key, 0)
    if not engine.round2_started:
        r2.pop('words', None)
        r2.pop('ciphertext', None)
    quality = float(row['quality_override']) if row['quality_override'] is not None else None
    state['quality_status'] = 'reviewed' if quality is not None else 'pending'
    state['quality_reviewed'] = row['quality_override'] is not None
    state['quality_reason'] = row['quality_reason']
    state['quality_score'] = quality
    r2['quality_marks'] = quality
    r2['quality_provisional'] = False
    r2['score'] = (quality or 0) + sum(engine.word_scores.values())
    state['objective_score'] = r1.get('score', 0) + sum(engine.word_scores.values())
    state['final_score'] = round(state['objective_score'] + quality, 2) if quality is not None else None
    state['total_score'] = round(r1.get('score', 0) + r2['score'], 2)
    return state

def get_state(token, history_after=None):
    with connect() as conn:
        team = authorized_team(conn, token)
        row, engine = load(conn, team, history_after=history_after)
        event = event_state(conn,team['batch_id'])
        refresh(engine, event)
        state = snapshot(engine, row, event)
        state['prompt_history_complete'] = history_after is None
        if history_after is not None:
            state['history_after'] = history_after
            state['prompt_history'] = [turn for turn in state['prompt_history'] if turn['turn'] > history_after]
        return state

def mutate(token, action, data):
    with transaction() as conn:
        team = authorized_team(conn, token)
        row, engine = load(conn, team)
        event = event_state(conn,team['batch_id'])
        refresh(engine, event)
        if event['status'] == 'waiting':
            raise EventError('Wait for the administrator to start the event.', 409)
        if row['pending_token'] and row['pending_until'] > time.time():
            raise EventError('Your previous prompt is still being processed.', 409)
        if row['pending_token']:
            # Supersede an expired provider request before changing game state.
            conn.execute('UPDATE game_sessions SET pending_token=NULL,pending_until=0 WHERE session_id=?', (engine.session_id,))
        if engine.is_finished:
            if action == 'answer':
                log_answer(conn, engine, team['batch_id'], data, None, 'closed')
            save(conn, engine)
            return {'state': snapshot(engine, row, event), 'message': 'Your session has finished.'}
        if action == 'timeline':
            placed = data.get('placed_ids')
            valid = {item['id'] for item in engine.timeline_events}
            if not isinstance(placed, list) or len(placed) != len(valid) or any(not isinstance(x,str) for x in placed) or set(placed) != valid:
                raise EventError('Place each timeline card exactly once before submitting.')
            if engine.round2_started:
                raise EventError('Round 1 submissions have closed.', 409)
            correct, slots, message = engine.check_timeline_submission(placed)
            conn.execute('INSERT INTO timeline_attempts(session_id,team_id,batch_id,submitted_at,attempt,placed_ids,slot_results,correct,score) VALUES(?,?,?,?,?,?,?,?,?)',
                (engine.session_id,engine.team_id,team['batch_id'],time.time(),engine.round1_attempts,json.dumps(placed),json.dumps(slots),int(correct),engine.round1_score))
            result = {'correct': correct, 'slot_results': slots, 'message': message}
        elif action == 'answer':
            if not engine.round2_started:
                raise EventError('Round 2 has not started.', 409)
            index = data.get('word_index', data.get('word_id'))
            if not valid_target(index):
                raise EventError('Choose word 1 or word 2.')
            answer = str(data.get('answer', '')).strip()
            if not answer or len(answer) > 100:
                raise EventError('Enter an answer up to 100 characters.')
            result = engine.submit_word(index, answer)
            log_answer(conn, engine, team['batch_id'], data, result.get('correct'), 'correct' if result.get('correct') else 'incorrect')
        elif action == 'finish':
            if not engine.round2_started:
                raise EventError('Round 2 has not started.', 409)
            finish_session(engine, 'submitted')
            result = {'message': 'Your score has been submitted.'}
        else:
            raise EventError('Unknown action.')
        save(conn, engine)
        return {**result, 'state': snapshot(engine, row, event)}

def prompt(token, data):
    message = str(data.get('message', data.get('prompt', ''))).strip()
    if not message or len(message) > 2000:
        raise EventError('Enter a prompt up to 2000 characters.')
    target = data.get('target')
    if target is not None and not valid_target(target):
        raise EventError('Choose word 1 or word 2.')
    reservation = secrets.token_hex(16)
    with transaction() as conn:
        team = authorized_team(conn, token)
        row, engine = load(conn, team)
        event = event_state(conn,team['batch_id'])
        refresh(engine, event)
        if event['status'] != 'running' or not engine.round2_started or engine.is_finished:
            raise EventError('Prompts are accepted only during Round 2.', 409)
        now = time.time()
        if row['pending_until'] > now and row['pending_token']:
            raise EventError('Your previous prompt is still being processed.', 409)
        if now - row['last_prompt_at'] < 1.5:
            raise EventError('Wait a moment before sending another prompt.', 429)
        if engine.round2_prompt_count >= 100:
            raise EventError('The 100-prompt session limit has been reached.', 429)
        save(conn, engine)
        conn.execute('UPDATE game_sessions SET pending_token=?,pending_until=?,last_prompt_at=? WHERE session_id=?',
                     (reservation, now + 90, now, engine.session_id))
    try:
        result = engine.process_prompt(message, target=target)
        if not result.get('error') and engine.prompt_history:
            engine.prompt_history[-1].update(submitted_at=now,response_at=time.time(),latency_seconds=round(time.time()-now,3))
        with transaction() as conn:
            current = conn.execute('SELECT * FROM game_sessions WHERE session_id=?', (engine.session_id,)).fetchone()
            if current['pending_token'] != reservation:
                raise EventError('This request expired. Refresh your session before trying again.', 409)
            event = event_state(conn,team['batch_id'])
            refresh(engine, event)
            if result.get('error'):
                details = {key:value for key,value in result.items() if key not in ('state',)}
                conn.execute('INSERT INTO failed_requests(session_id,team_id,batch_id,submitted_at,prompt,target,error,reason,retry_seconds,details) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (engine.session_id,engine.team_id,team['batch_id'],now,message,str(target) if target is not None else None,str(result['error']),
                     str(result.get('ai_fallback_reason','provider_unavailable')),int(result.get('ai_retry_after_seconds',0)),json.dumps(details)))
            save(conn, engine)
            conn.execute('UPDATE game_sessions SET pending_token=NULL,pending_until=0 WHERE session_id=?', (engine.session_id,))
            response = {**result, 'state': snapshot(engine, current, event)}
        if result.get('error'):
            raise EventError(str(result['error']),503,response)
        return response
    finally:
        with transaction() as conn:
            conn.execute('UPDATE game_sessions SET pending_token=NULL,pending_until=0 WHERE pending_token=?', (reservation,))

def start_event(batch_id=None):
    with transaction() as conn:
        event = event_state(conn,batch_id)
        if event['batch_id'] != event['active_batch_id']:
            raise EventError('Activate this event session before starting it.',409)
        if event['status'] == 'ended':
            raise EventError('This event session has ended. Open the next session instead.',409)
        if event['started_at'] is None:
            if not conn.execute('SELECT COUNT(*) FROM teams WHERE batch_id=?',(event['batch_id'],)).fetchone()[0]:
                raise EventError('Register at least one team before starting.',409)
            conn.execute('UPDATE event_sessions SET started_at=? WHERE batch_id=?',(time.time(),event['batch_id']))
        return event_state(conn,event['batch_id'])


def end_event(batch_id=None):
    with transaction() as conn:
        event = event_state(conn,batch_id)
        if event['batch_id'] != event['active_batch_id'] and not event['ended_at']:
            raise EventError('Only the active event session can be closed.',409)
        if not event['ended_at']:
            conn.execute('UPDATE event_sessions SET ended_at=? WHERE batch_id=?',(time.time(),event['batch_id']))
        event = event_state(conn,event['batch_id'])
        for team in conn.execute('SELECT * FROM teams WHERE batch_id=?',(event['batch_id'],)).fetchall():
            row, engine = load(conn,team)
            refresh(engine,event)
            if not row['pending_token'] or row['pending_until'] < time.time():
                if row['pending_token']:
                    conn.execute('UPDATE game_sessions SET pending_token=NULL,pending_until=0 WHERE session_id=?',(engine.session_id,))
                save(conn,engine)
        return event


def activate_batch(batch_id):
    if not isinstance(batch_id,str) or not batch_id:
        raise EventError('Choose Morning or Afternoon.')
    with transaction() as conn:
        current, target = event_state(conn), event_state(conn,batch_id)
        if current['batch_id'] == target['batch_id']:
            return current
        occupied = conn.execute('SELECT COUNT(*) FROM teams WHERE batch_id=?',(current['batch_id'],)).fetchone()[0]
        if current['status'] == 'running' or (current['status']=='waiting' and occupied):
            raise EventError('Close the current session before opening registration for the next session.',409)
        if target['status'] != 'waiting':
            raise EventError('Only a session that has not started can open registration.',409)
        conn.execute('UPDATE event SET active_batch_id=? WHERE id=1',(target['batch_id'],))
        return event_state(conn)


def log_answer(conn,engine,batch_id,data,correct,outcome):
    conn.execute('INSERT INTO word_answers(session_id,team_id,batch_id,submitted_at,word_index,answer,correct,outcome) VALUES(?,?,?,?,?,?,?,?)',
        (engine.session_id,engine.team_id,batch_id,time.time(),str(data.get('word_index',data.get('word_id',''))),str(data.get('answer',''))[:100],int(correct) if correct is not None else None,outcome))


def admin_sessions(batch_id=None):
    with connect() as conn:
        event = event_state(conn,batch_id)
        result = []
        for team in conn.execute('SELECT * FROM teams WHERE batch_id=? ORDER BY registered_at',(event['batch_id'],)).fetchall():
            row, engine = load(conn,team,include_history=False)
            refresh(engine,event)
            state = snapshot(engine,row,event)
            result.append({'session_id':engine.session_id,**team_dict(team),'phase':state['phase'],
                'round1_score':state['round1'].get('score',0),'word1_score':engine.word_scores.get('word1',0),
                'word2_score':engine.word_scores.get('word2',0),'quality_score':state.get('quality_score'),
                'quality_reviewed':state.get('quality_reviewed',False),'quality_status':state.get('quality_status','pending'),
                'objective_score':state.get('objective_score',0),'final_score':state.get('final_score'),
                'total_score':state['total_score'],'prompt_count':engine.round2_prompt_count})
        return {'sessions':result,'event':event,'batches':list_batches(conn),'total':len(result)}


def admin_detail(session_id):
    with connect() as conn:
        row = conn.execute('SELECT * FROM game_sessions WHERE session_id=?',(session_id,)).fetchone()
        if not row:
            raise EventError('Session not found.',404)
        team = conn.execute('SELECT * FROM teams WHERE team_id=?',(row['team_id'],)).fetchone()
        engine = TimeglitchSession.from_storage(json.loads(row['state']))
        event = event_state(conn,team['batch_id'])
        refresh(engine,event)
        audit = [dict(item) for item in conn.execute('SELECT score,reason,reviewed_at FROM quality_audit WHERE session_id=? ORDER BY id',(session_id,))]
        failed = []
        for item in conn.execute('SELECT * FROM failed_requests WHERE session_id=? ORDER BY id',(session_id,)):
            record=dict(item)
            record['timestamp']=record['submitted_at']
            record['message']=record['prompt']
            record['ai_fallback_reason']=record['reason']
            record['ai_retry_after_seconds']=record['retry_seconds']
            record['provider_details']=json.loads(record.pop('details'))
            failed.append(record)
        return {'session':snapshot(engine,row,event),'messages':engine.prompt_history,'quality_audit':audit,'failed_requests':failed,
            'timeline_attempts':[dict(item) for item in conn.execute('SELECT * FROM timeline_attempts WHERE session_id=? ORDER BY id',(session_id,))],
            'word_answers':[dict(item) for item in conn.execute('SELECT * FROM word_answers WHERE session_id=? ORDER BY id',(session_id,))]}


def validate_review(score,reason):
    if isinstance(score,bool) or not isinstance(score,(float,int)) or not 0<=score<=4 or not isinstance(reason,str) or not reason.strip() or len(reason.strip())>1000:
        raise EventError('Enter a score from 0 to 4 and an explanation up to 1000 characters.')
    return score,reason.strip()


def write_review(conn,session_id,score,reason):
    now=time.time()
    conn.execute('UPDATE game_sessions SET quality_override=?,quality_reason=?,quality_reviewed_at=? WHERE session_id=?',(score,reason,now,session_id))
    conn.execute('INSERT INTO quality_audit(session_id,score,reason,reviewed_at) VALUES(?,?,?,?)',(session_id,score,reason,now))


def review_quality(session_id,data):
    score,reason=validate_review(data.get('score'),data.get('reason'))
    with transaction() as conn:
        row=conn.execute('SELECT teams.batch_id FROM game_sessions JOIN teams ON game_sessions.team_id=teams.team_id WHERE session_id=?',(session_id,)).fetchone()
        if not row:
            raise EventError('Session not found.',404)
        if event_state(conn,row['batch_id'])['status']!='ended':
            raise EventError('Prompt quality can be graded after this event session ends.',409)
        write_review(conn,session_id,score,reason)
    return admin_detail(session_id)


def apply_reviews(reviews,dry_run=True):
    if not reviews:
        raise EventError('The review file has no completed grades.')
    seen=set()
    validated=[]
    with transaction() as conn:
        for review in reviews:
            score,reason=validate_review(review.get('score'),review.get('reason'))
            key=(review.get('batch_id'),review.get('team_id'))
            if key in seen:
                raise EventError('The review file repeats a team in the same session.')
            seen.add(key)
            row=conn.execute('SELECT game_sessions.session_id FROM game_sessions JOIN teams ON game_sessions.team_id=teams.team_id WHERE teams.batch_id=? AND teams.team_id=?',key).fetchone()
            if not row:
                raise EventError('A reviewed team does not belong to the specified event session.')
            if event_state(conn,key[0])['status']!='ended':
                raise EventError('Every reviewed event session must have ended.',409)
            validated.append((row['session_id'],score,reason))
        if not dry_run:
            for values in validated:
                write_review(conn,*values)
    return {'validated':len(validated),'applied':0 if dry_run else len(validated),'dry_run':dry_run}
