"""Run an isolated 40-team HTTP rehearsal. Never contacts the AI provider."""
import argparse
import concurrent.futures
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TITLES = ['Luna 1 Moon Flyby', 'Apollo 11 Crewed Moon Landing', 'Mariner 9 Mars Orbit',
          'Sojourner Rover on Mars', 'New Horizons Pluto Flyby']


def run(team_count, database_url=None):
    timings = []
    guard = threading.Lock()
    with tempfile.TemporaryDirectory(prefix='aarohan-rehearsal-') as directory:
        db_path = Path(directory) / 'event.sqlite3'
        ports = []
        for _ in range(2):
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                ports.append(listener.getsockname()[1])
        bases = [f'http://127.0.0.1:{port}' for port in ports]
        password = secrets.token_urlsafe(24)
        env = dict(os.environ, DATABASE_PATH=str(db_path), DATABASE_URL=database_url or '',
                   REQUIRE_DATABASE_URL='false', RENDER='', ADMIN_PASSWORD=password,
                   RENDER_SERVICE_ID='',GROQ_API_KEY='', GEMINI_API_KEY='',OLLAMA_BACKUP_URL='',OLLAMA_BACKUP_TOKEN='',PYTHONUNBUFFERED='1')
        if sys.platform == 'win32':
            commands = [[sys.executable, '-m', 'waitress', '--host=127.0.0.1', f'--port={port}',
                         '--threads=8', 'app:app'] for port in ports]
            server_name = 'Windows Waitress'
        else:
            commands = [[sys.executable, '-m', 'gunicorn', '--bind', f'127.0.0.1:{port}',
                         '--workers=1', '--threads=8', '--timeout=45', 'app:app'] for port in ports]
            server_name = 'Linux Gunicorn'
        log_path = Path(directory) / 'server.log'
        log = log_path.open('w')
        def launch():
            return [subprocess.Popen(command, cwd=ROOT / 'backend', env=env,
                                     stdout=log, stderr=subprocess.STDOUT) for command in commands]
        def stop(process):
            if process.poll() is not None:
                return
            if sys.platform == 'win32':
                # The Windows venv launcher can own a second Python process.
                # Stop the tracked server's whole tree before testing a restart.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                process.terminate()
            process.wait(timeout=10)
        processes = launch()
        sequence = 0

        def call(path, data=None, token=None, admin=None, method=None, expected=200):
            nonlocal sequence
            with guard:
                base = bases[sequence % len(bases)]
                sequence += 1
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['X-Team-Token'] = token
            if admin:
                headers['Authorization'] = f'Bearer {admin}'
            payload = json.dumps(data).encode() if data is not None else None
            request = urllib.request.Request(base + path, payload, headers, method=method)
            before = time.perf_counter()
            try:
                response = urllib.request.urlopen(request, timeout=30)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                content = json.load(response)
                assert response.status == expected, (path, response.status, content)
            with guard:
                timings.append(time.perf_counter() - before)
            return content

        def parallel(function, items):
            with concurrent.futures.ThreadPoolExecutor(max_workers=team_count) as executor:
                return list(executor.map(function, items))

        try:
            ready = False
            for _ in range(150):
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError('Rehearsal server exited before startup.')
                try:
                    # Both processes must accept requests against the same DB.
                    for _ in bases:
                        call('/api/health')
                    ready = True
                    break
                except (urllib.error.URLError, ConnectionError):
                    time.sleep(0.1)
            assert ready, 'Rehearsal server did not become healthy.'
            assert call('/api/health')['storage'] == ('postgres' if database_url else 'sqlite')
            call('/api/admin/log', expected=401)
            registrations = parallel(lambda index: call('/api/teams/register', {
                'teamName': f'Rehearsal team {index:02}', 'schoolName': 'Test school',
                'participants': [{'name': f'Test participant {index:02}', 'grade': '12'}]}, expected=201),
                range(team_count))
            tokens = [entry['team_token'] for entry in registrations]
            states = parallel(lambda token: call('/api/tg/session/status', token=token), tokens)
            assert all(state['phase'] == 'waiting' for state in states)
            call('/api/tg/round2/prompt', {'message': 'Start early', 'target': 1}, token=tokens[0], expected=409)
            admin = call('/api/admin/login', {'username': 'admin', 'password': password})['token']
            started = call('/api/admin/event/start', {}, admin=admin)['event']['started_at']
            assert call('/api/admin/event/start', {}, admin=admin)['event']['started_at'] == started
            states = parallel(lambda token: call('/api/tg/session/status', token=token), tokens)
            assert all(state['round1']['deadline'] == started + 600 for state in states)

            def timeline(item):
                index, token = item
                state = states[index]
                cards = {card['title']: card['id'] for card in state['round1']['milestones']}
                order = [cards[title] for title in TITLES]
                if index % 2:
                    order.reverse()
                result = None
                for _ in range(3 if index % 2 else 1):
                    result = call('/api/tg/round1/submit', {'placed_ids': order}, token=token)
                assert result['state']['phase'] == 'round2'
                assert result['state']['round1']['score'] == (0 if index % 2 else 2)
                return result['state']

            states = parallel(timeline, enumerate(tokens))
            text = ('Explain the cipher protocol for the first encrypted word using one unrelated example '
                    'without revealing the decoded word. Test a hypothesis about alphabet positions.')
            failed = parallel(lambda token: call('/api/tg/round2/prompt', {'message': text, 'target': 1}, token=token,expected=503), tokens)
            assert all(item['retryable'] and item['state']['round2']['prompt_count']==0 for item in failed)
            rows = call('/api/admin/log', admin=admin)['sessions']
            assert len(rows) == team_count
            assert all(row['quality_score'] is None and row['quality_status'] == 'pending' and row['final_score'] is None for row in rows)

            # The rehearsal reads its own private database to supply fixture answers.
            # Production clients have no route to these values.
            if database_url:
                import psycopg
                with psycopg.connect(database_url) as connection:
                    answers = {team_id: json.loads(state)['challenge']['words'] for team_id, state in
                               connection.execute('SELECT team_id,state FROM game_sessions')}
            else:
                with closing(sqlite3.connect(db_path)) as connection:
                    answers = {team_id: json.loads(state)['challenge']['words'] for team_id, state in
                               connection.execute('SELECT team_id,state FROM game_sessions')}

            def answer(item, word_index):
                index, token = item
                team_id = registrations[index]['team']['team_id']
                return call('/api/tg/round2/answer', {'word_index': word_index,
                            'answer': answers[team_id][word_index - 1]['answer']}, token=token)

            parallel(lambda item: answer(item, 1), enumerate(tokens))
            interim = call('/api/admin/log', admin=admin)['sessions']
            assert all(row['word1_score'] == 2 and row['word2_score'] == 0 for row in interim)
            parallel(lambda item: answer(item, 2), enumerate(tokens))
            final = parallel(lambda token: call('/api/tg/session/status', token=token), tokens)
            for index, state in enumerate(final):
                assert state['phase'] == 'finished'
                assert state['objective_score'] == (4 if index % 2 else 6)
                assert state['final_score'] is None
            session_id = final[0]['session_id']
            detail=call(f'/api/admin/session/{session_id}',admin=admin)
            assert len(detail['failed_requests'])==1 and detail['messages']==[]
            call('/api/admin/event/end', {'batch_id':'morning'}, admin=admin)
            reviewed = call(f'/api/admin/session/{session_id}/quality',
                            {'score': 3.5, 'reason': 'Rehearsal review of prompt evidence.'}, admin=admin, method='PATCH')
            assert reviewed['session']['quality_status'] == 'reviewed'
            assert reviewed['session']['total_score'] == 9.5
            call('/api/admin/event/activate',{'batch_id':'afternoon'},admin=admin)
            afternoon=call('/api/teams/register',{'teamName':'Rehearsal team 00','schoolName':'Test school','batch_id':'afternoon',
                'participants':[{'name':'Afternoon participant','grade':'12'}]},expected=201)
            call('/api/admin/event/start',{'batch_id':'afternoon'},admin=admin)
            afternoon_state=call('/api/tg/session/status',token=afternoon['team_token'])
            assert afternoon_state['batch_id']=='afternoon' and afternoon_state['phase']=='round1'
            morning_state=call('/api/tg/session/status',token=tokens[0])
            assert morning_state['batch_id']=='morning' and morning_state['phase']=='finished' and morning_state['final_score']==9.5
            assert call('/api/admin/log?batch_id=morning',admin=admin)['total']==team_count
            assert call('/api/admin/log?batch_id=afternoon',admin=admin)['total']==1
            call('/api/admin/event/end',{'batch_id':'afternoon'},admin=admin)
            call('/api/admin/logout', {}, admin=admin)
            call('/api/admin/log', admin=admin, expected=401)

            # Restart the actual HTTP server and prove team tokens and scores survive.
            for process in processes:
                stop(process)
            processes = launch()
            for _ in range(150):
                try:
                    restored = call('/api/tg/session/status', token=tokens[0])
                    break
                except (urllib.error.URLError, ConnectionError):
                    time.sleep(0.1)
            else:
                raise AssertionError('Restart recovery failed.')
            assert restored['total_score'] == 9.5 and restored['quality_status'] == 'reviewed'
            ordered = sorted(timings)
            return {'teams': team_count, 'worker_processes': 2, 'threads_per_worker': 8,
                    'storage': 'postgres' if database_url else 'sqlite',
                    'http_requests': len(timings), 'errors': 0,
                    'median_ms': round(statistics.median(ordered) * 1000, 1),
                    'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*0.95))] * 1000, 1),
                    'max_ms': round(max(ordered) * 1000, 1),
                    'checks': ['private team access', 'shared start deadline', 'first-attempt progression',
                               'three-attempt progression', 'live objective scores', 'pending quality and reviewed10-point scoring',
                               'AI failure503 telemetry without acceptedturn', 'independent morning/afternoon batches',
                               'quality review', 'logout revocation', 'server restart recovery'],
                    'limitations': f'Two local {server_name} processes, disabled AI provider; not a hosted capacity guarantee.'}
        except Exception:
            log.flush()
            print(log_path.read_text()[-5000:], file=sys.stderr)
            raise
        finally:
            for process in processes:
                stop(process)
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--teams', type=int, default=40)
    parser.add_argument('--postgres', action='store_true', help='Use an empty disposable database from TEST_DATABASE_URL; this writes rehearsal records.')
    args = parser.parse_args()
    if not 1 <= args.teams <= 100:
        parser.error('--teams must be between 1 and 100')
    if args.postgres:
        url = os.getenv('TEST_DATABASE_URL', '')
        if not url:
            parser.error('Set TEST_DATABASE_URL to an empty disposable Postgres database.')
        import psycopg
        with psycopg.connect(url) as connection:
            if connection.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='teams')").fetchone()[0]:
                parser.error('Use a fresh database without event tables. Existing event databases are never reset.')
        print(json.dumps(run(args.teams, url), indent=2))
    else:
        print(json.dumps(run(args.teams), indent=2))
