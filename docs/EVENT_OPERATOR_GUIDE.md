# Event operator guide

## How the application works

Flask serves the team pages and API from one site. On the hosted version, Render runs the app and Neon Postgres stores event data. On a Windows laptop, the app can use SQLite for local development. The server owns registration, session selection, clocks, timeline attempts, cipher hints, answer checks and objective marks.

Teams register for either Morning or Afternoon. Each team receives a private resume code and waits until an organizer starts that session. Starting a session starts the five-minute timeline part for every registered team at once. A correct order earns 2 marks and moves that team straight to the 15-minute prompt-engineering part. Three wrong attempts or the five-minute deadline also moves the team forward, without the 2 timeline marks. In the prompt part, teams ask the chatbot for hints about two words, decode them and submit each answer. Each correct word earns 2 marks.

The dashboard shows timeline and word marks, up to 6. The remaining 4 marks come from the prompt-quality review after a session ends. The app saves prompts, replies, failed AI requests and submissions for organizers to review and export. The chatbot does not assign prompt-quality marks.

## Start a local Windows server

Use Python 3.12. In PowerShell, open the repository folder and run the setup commands once:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and set a private `ADMIN_PASSWORD` and `GROQ_API_KEY`. Keep this file private. It is excluded from Git. Groq is the primary model provider. Ollama is optional and only used as a backup when configured and reachable. Local Windows startup uses SQLite unless `DATABASE_URL` is configured.

Start the server by running `start_station.bat`. Keep its command window open. The default URLs are:

- Teams: `http://localhost:5000/`
- Organizer login: `http://localhost:5000/admin-login`
- Health check: `http://localhost:5000/api/health`

Other laptops must open the host laptop's network address, not `localhost`. The venue network must allow those systems to reach the host on port 5000. For the event, prefer one shared hosted HTTPS URL so all teams and the organizer use the same database and server.

## Use the hosted server

The hosting configuration targets a Render Free web service connected to the event's Neon Postgres database. Hosted startup requires `DATABASE_URL`; it refuses to run against Render's temporary local filesystem. The app uses Gunicorn on Render. The Render service and public URL are not yet confirmed as deployed, and the Neon application connection and live restart recovery remain outstanding. Do not send teams a URL until the readiness checks in [READINESS.md](READINESS.md) and [DEPLOYMENT.md](../DEPLOYMENT.md) pass.

When the service is available, check `/api/health` and confirm that storage reports Postgres. Sign in at `/admin-login`, open `/admin`, and check that the correct session is selected. Open the team URL from a second device and verify that it reaches the same event. Render Free can sleep when idle, so open the site and admin before registration and allow the service to wake.

## Before each session

1. Confirm the correct deployment URL and that `/api/health` reports Postgres for the hosted event.
2. Sign in to the admin page. Check the AI status and remaining budget. A configured key is not proof of a successful live reply; run a team rehearsal prompt and check its response.
3. Verify the intended cipher catalog is active. The repository's public catalog is rehearsal data. The private competition catalog is local and is not active until it is configured in the hosting environment.
4. Select Morning or Afternoon and open registration for that session. Do not use an old team's resume code for a different session.
5. Register a test team and confirm it waits in the lobby. Check team names, schools and participant counts in admin.
6. Start the session once, when all teams are ready. This starts the five-minute timeline clock for all registered teams together. Tell teams that the server clock continues if they refresh or leave the tab.
7. Confirm the organizer can see the live roster and objective marks. Avoid restarting or changing deployment settings during play.

The event uses separate Morning and Afternoon records. Before opening the second session, end the first session in admin and export its results. Then select Afternoon and open its registration. Morning registrations and results remain attached to Morning.

## After each session

1. End the session in admin when play is over. Ending makes its results available for prompt-quality review.
2. Select that session and use **Export Excel**. Store the workbook privately because it contains participant information and full prompt transcripts. Keep a separate export for Morning and Afternoon.
3. Review the prompt transcripts after play. Award up to 4 marks with the rubric in [PROMPT_SCORING.md](PROMPT_SCORING.md). The objective score is worth up to 6, for a total of 10.
4. If grading outside the dashboard, keep `batch_id` and `team_id` unchanged. Validate the workbook before applying it. The commands below run from the repository root:

   ```powershell
   .\.venv\Scripts\python.exe backend\grade_reviews.py .\morning-grades.xlsx
   .\.venv\Scripts\python.exe backend\grade_reviews.py .\morning-grades.xlsx --apply
   ```

5. Download a fresh workbook after grading so it contains final scores and the review audit history.

For a local SQLite event, make an additional consistent database backup after the session. Choose a new destination filename; the backup command will not overwrite an existing file:

```powershell
.\.venv\Scripts\python.exe backend\backup_event.py backend\data\event.sqlite3 C:\EventBackups\aarohan-morning.sqlite3
```

For the hosted event, download each session's workbook and arrange a database backup using the Neon account's backup tools. Render's filesystem is temporary, so do not store event data there.

## Current release checks

Automated application and frontend checks are recorded in [VERIFICATION.md](VERIFICATION.md). The cloud deployment, live Neon connection and recovery after a hosted restart, competition catalog activation, real browser layout review, venue network rehearsal and sustained AI capacity for 30 to 40 teams still need live checks. See [READINESS.md](READINESS.md) for the completion criteria. Free provider capacity can run out during a burst; a retryable AI error does not pause the event clock.
