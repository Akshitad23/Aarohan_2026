"""Same-origin Flask server for the Aarohan event."""
import csv
import io
import os
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory
from dotenv import load_dotenv

load_dotenv(os.getenv('AAROHAN_ENV_FILE') or Path(__file__).parent / '.env')
from logger_db import DATABASE_ERRORS, connect, init_db, storage_kind, transaction
import event_service as service
from ai_client import get_ai_status, init_client
from ciphers import get_challenge

FRONTEND_DIR = Path(__file__).parent.parent / 'frontend'
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 32768
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
# Reject an invalid private catalog before the server advertises healthy status.
get_challenge('startup-validation')
init_db()
if os.getenv('GROQ_API_KEY'):
    try:
        init_client(os.environ['GROQ_API_KEY'])
    except Exception as error:
        app.logger.warning('AI client initialization failed (%s).', type(error).__name__)

def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise service.EventError('Send a JSON object.', 400)
    return data

def team_token():
    return request.headers.get('X-Team-Token', '').strip()

def admin_authorized():
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    token = token or request.headers.get('X-Admin-Key', '').strip()
    if not token:
        return False
    with connect() as conn:
        row = conn.execute('SELECT expires_at FROM admin_sessions WHERE token_hash=?', (service.digest(token),)).fetchone()
    return bool(row and row['expires_at'] > time.time())

def admin_required(func):
    @wraps(func)
    def checked(*args, **kwargs):
        if not admin_authorized():
            raise service.EventError('Administrator authentication is required.', 401)
        return func(*args, **kwargs)
    return checked

@app.errorhandler(service.EventError)
def event_error(error):
    return jsonify({'error':str(error),**error.details}), error.status

def database_error(error):
    app.logger.error('Database operation failed (%s).', type(error).__name__)
    return jsonify(error='The server is busy. Wait a moment and retry.'), 503

for database_exception in DATABASE_ERRORS:
    app.register_error_handler(database_exception, database_error)

@app.after_request
def secure_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/')
@app.get('/register')
def registration_page():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.get('/game')
def game_page():
    return send_from_directory(FRONTEND_DIR, 'game.html')

@app.get('/admin')
def admin_page():
    return send_from_directory(FRONTEND_DIR, 'admin.html')

@app.get('/admin-login')
def admin_login_page():
    return send_from_directory(FRONTEND_DIR, 'admin-login.html')

@app.post('/api/teams/register')
def register_team():
    return jsonify(service.register(body())), 201

@app.get('/api/event/status')
def event_status():
    with connect() as conn:
        event = service.event_state(conn)
        count = conn.execute('SELECT COUNT(*) FROM teams WHERE batch_id=?',(event['batch_id'],)).fetchone()[0]
        batches = service.list_batches(conn)
    return jsonify(event=event,batches=batches,active_batch_id=event['batch_id'],registered_teams=count,server_time=time.time())

@app.post('/api/tg/session/start')
def start_session():
    return jsonify(service.get_state(team_token()))

@app.get('/api/tg/session/status')
def session_status():
    after = request.args.get('history_after')
    if after is not None:
        try:
            after = int(after)
            if after < 0:
                raise ValueError
        except ValueError:
            raise service.EventError('history_after must be a nonnegative turn number.')
    return jsonify(service.get_state(team_token(), history_after=after))

@app.post('/api/tg/round1/submit')
def timeline_submit():
    return jsonify(service.mutate(team_token(), 'timeline', body()))

@app.post('/api/tg/round2/prompt')
def prompt():
    return jsonify(service.prompt(team_token(), body()))

@app.post('/api/tg/round2/answer')
def answer():
    return jsonify(service.mutate(team_token(), 'answer', body()))

@app.post('/api/tg/round2/finish')
def finish():
    return jsonify(service.mutate(team_token(), 'finish', body()))

@app.post('/api/admin/login')
def admin_login():
    data = body()
    if not ADMIN_PASSWORD:
        raise service.EventError('Set ADMIN_PASSWORD on the server before using administrator controls.', 503)
    address = request.remote_addr or 'unknown'
    now = time.time()
    with transaction() as conn:
        row = conn.execute('SELECT * FROM login_limits WHERE address=?', (address,)).fetchone()
        if row and now - row['window_start'] < 300 and row['count'] >= 15:
            raise service.EventError('Too many login attempts. Wait five minutes before retrying.', 429)
        count = row['count'] + 1 if row and now - row['window_start'] < 300 else 1
        window = row['window_start'] if row and now - row['window_start'] < 300 else now
        conn.execute('INSERT INTO login_limits(address,count,window_start) VALUES(?,?,?) ON CONFLICT(address) DO UPDATE SET count=excluded.count,window_start=excluded.window_start', (address, count, window))
    username = str(data.get('username', '')).strip().lower()
    password = str(data.get('password', ''))
    if username not in ('admin', 'admin@aarohan.org') or not secrets.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        raise service.EventError('Invalid administrator credentials.', 401)
    token = secrets.token_urlsafe(32)
    with transaction() as conn:
        conn.execute('DELETE FROM login_limits WHERE address=?', (address,))
        conn.execute('DELETE FROM admin_sessions WHERE expires_at<?', (now,))
        conn.execute('INSERT INTO admin_sessions(token_hash,expires_at) VALUES(?,?)', (service.digest(token), now + 86400))
    return jsonify(success=True, token=token, user='Aarohan administrator', expires_at=now+86400)

@app.post('/api/admin/logout')
@admin_required
def admin_logout():
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip() or request.headers.get('X-Admin-Key', '').strip()
    with transaction() as conn:
        conn.execute('DELETE FROM admin_sessions WHERE token_hash=?', (service.digest(token),))
    return jsonify(success=True)

@app.get('/api/admin/event/status')
@admin_required
def admin_event_status():
    return event_status()

@app.post('/api/admin/event/start')
@admin_required
def event_start():
    data=body() if request.data else {}
    return jsonify(event=service.start_event(data.get('batch_id')))

@app.post('/api/admin/event/end')
@admin_required
def event_end():
    data=body() if request.data else {}
    return jsonify(event=service.end_event(data.get('batch_id')))

@app.post('/api/admin/event/activate')
@admin_required
def event_activate():
    return jsonify(event=service.activate_batch(body().get('batch_id')))

@app.get('/api/admin/teams')
@admin_required
def admin_teams():
    with connect() as conn:
        event=service.event_state(conn,request.args.get('batch_id'))
        teams = [service.team_dict(row, True) for row in conn.execute('SELECT * FROM teams WHERE batch_id=? ORDER BY registered_at',(event['batch_id'],))]
    return jsonify(teams=teams, stats={'total_teams':len(teams),'total_participants':sum(t['team_size'] for t in teams),
                                      'unique_schools':len({t['school_name'].lower() for t in teams})})

@app.post('/api/admin/teams/<team_id>/token')
@admin_required
def recover_team(team_id):
    token = secrets.token_urlsafe(32)
    with transaction() as conn:
        row = conn.execute('SELECT * FROM teams WHERE team_id=?', (team_id,)).fetchone()
        if not row:
            raise service.EventError('Team not found.', 404)
        conn.execute('UPDATE teams SET token_hash=? WHERE team_id=?', (service.digest(token), team_id))
    return jsonify(team=service.team_dict(row), team_token=token)

@app.get('/api/admin/log')
@admin_required
def admin_log():
    return jsonify(service.admin_sessions(request.args.get('batch_id')))

@app.get('/api/admin/session/<session_id>')
@admin_required
def admin_session(session_id):
    return jsonify(service.admin_detail(session_id))

@app.patch('/api/admin/session/<session_id>/quality')
@admin_required
def quality_review(session_id):
    return jsonify(service.review_quality(session_id, body()))


def csv_cell(value):
    value = str(value if value is not None else '')
    return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value

@app.get('/api/admin/export')
@admin_required
def export_scores():
    rows = service.admin_sessions(request.args.get('batch_id'))['sessions']
    fields = ['batch_id','team_id','team_name','school_name','phase','round1_score','word1_score','word2_score','objective_score','quality_score','quality_status','final_score','prompt_count']
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.DictWriter(output, fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: csv_cell(row.get(key)) for key in fields})
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=aarohan-scores.csv'})

@app.get('/api/admin/teams/export')
@admin_required
def export_teams():
    with connect() as conn:
        event=service.event_state(conn,request.args.get('batch_id'))
        rows = [service.team_dict(row, True) for row in conn.execute('SELECT * FROM teams WHERE batch_id=? ORDER BY registered_at',(event['batch_id'],))]
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['team_id','team_name','school_name','participant_name','grade'])
    for row in rows:
        for participant in row['participants']:
            writer.writerow([csv_cell(x) for x in [row['team_id'],row['team_name'],row['school_name'],participant['name'],participant['grade']]])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=aarohan-teams.csv'})

@app.get('/api/admin/export.xlsx')
@admin_required
def export_workbook():
    from export_xlsx import export_batch
    payload,batch_id=export_batch(request.args.get('batch_id'))
    return Response(payload,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':f'attachment; filename=aarohan-{batch_id}.xlsx'})

@app.get('/api/health')
def health():
    with connect() as conn:
        conn.execute('SELECT 1').fetchone()
    ai = get_ai_status()
    return jsonify(status='ok', storage=storage_kind(), admin_configured=bool(ADMIN_PASSWORD),
                   ai_configured=ai['configured'], ai=ai)

# Retired password-game routes must never mutate cipher-event state.
@app.route('/api/<path:unused>', methods=['GET','POST','PATCH','DELETE'])
def retired_api(unused):
    return jsonify(error='This endpoint is unavailable. Refresh the event page.'), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=False, threaded=True)
