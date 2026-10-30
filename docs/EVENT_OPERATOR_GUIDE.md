# Event operator guide

## How the application works

Flask serves the team pages and API from one site. On the hosted version, Render runs the app and Neon Postgres stores event data. On a Windows laptop, the app can use SQLite for local development. The server owns registration, session selection, clocks, timeline attempts, cipher hints, answer checks and objective marks.

Teams register for Test, Morning or Afternoon. Test is a separate venue rehearsal using public rehearsal ciphers; it never receives the private competition catalog. Test data, Morning results and Afternoon results stay in separate sessions. Each team waits until an organizer starts that session. Starting a session starts the five-minute timeline part for every registered team at once. A correct order earns 2 marks and moves that team straight to the 15-minute prompt-engineering part. Three wrong attempts or the five-minute deadline also moves the team forward, without the 2 timeline marks. In the prompt part, teams ask the chatbot for hints about two words, decode them and submit each answer. Each correct word earns 2 marks.

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

The hosted event URL is [ai-think-hack-create.onrender.com](https://ai-think-hack-create.onrender.com). Render runs the Flask app with Gunicorn, and Neon Postgres stores event data. Hosted startup requires `DATABASE_URL` and refuses to use Render's temporary local filesystem. The Render service and database health check are live. Before admitting teams, complete the rehearsal and remaining checks in [READINESS.md](READINESS.md) and [DEPLOYMENT.md](../DEPLOYMENT.md).

When the service is available, check `/api/health` and confirm that storage reports Postgres. Sign in at `/admin-login`, open `/admin`, and check that the correct session is selected. Open the team URL from a second device and verify that it reaches the same event. Render Free can sleep when idle, so open the site and admin before registration and allow the service to wake.

## Before each session

1. Confirm the correct deployment URL and that `/api/health` reports Postgres for the hosted event.
2. Sign in to the admin page. Check the AI status and remaining budget. A configured key is not proof of a successful live reply; run a team rehearsal prompt and check its response.
3. Verify the private competition catalog is active. It is configured in Render as the masked `CIPHER_CATALOG_JSON` environment variable. Do not paste its contents into a student-facing page or public repository.
4. Before Morning, use the Test session for the venue rehearsal in [the final runbook](FINAL_EVENT_RUNBOOK.md). End Test, select Morning, and click **Open registration for this session** before inviting competition teams. For the second competition session, select Afternoon after ending and exporting Morning. Team progress stays with its original session. A 5-character transfer code expires after 10 minutes, works once, and moves access to another computer.
5. As competition teams register, confirm their names, schools, participant counts and waiting status in admin. Use the isolated local rehearsal for fake teams; do not add a test team to the live session.
6. Start the session once, when all teams are ready. This starts the five-minute timeline clock for all registered teams together. Tell teams that the server clock continues if they refresh or leave the tab.
7. Confirm the organizer can see the live roster and objective marks. Avoid restarting or changing deployment settings during play.

## If Render or the chatbot fails

The organizer laptop can serve as the app host. It uses the same Neon production database, so teams keep their registration, clocks, prompts and scores when they switch URLs. The launcher refuses to start unless it can reach Neon and validate the private catalog. Prepare it before the event using [the Windows fallback instructions](WINDOWS_FALLBACK.md); do not wait for an outage to copy secrets or install a model.

If Render is unavailable for more than two minutes, start `start_event_fallback.bat` on the wired, awake organizer laptop. Run `ipconfig`, find its Wi-Fi IPv4 address, then have every team and the admin open `http://<IPv4-address>:5000/` and sign in again if asked. Keep everyone on that one URL for the rest of the session. If a team changes computers, generate a 5-character transfer code from its saved team page or ask an organizer to issue one in admin. The code expires after 10 minutes and works once. Using it moves the team's access to the new computer. The laptop and venue Wi-Fi must allow inbound connections on port 5000. Never continue on a second local SQLite database.

If the website works but Groq is unavailable, the fallback app on the organizer laptop can use the configured local Ollama model. If the current API key is invalid or revoked, replace it with a valid key. A new key in the same Groq organization does not fix an organization rate limit or outage. The local Ollama path is the prepared no-cost alternative; it must be warmed and rehearsed before the event. If both model providers fail, stop prompting temporarily and tell the organizer. The game clock does not pause automatically. If Neon itself is unreachable, stop play and record the remaining work offline; do not switch to SQLite because it would split the event records.

Test, Morning and Afternoon each have separate records. Test is for the pre-event venue check only. Before opening Afternoon, end Morning and export it. Then select Afternoon and open its registration. Morning registrations and results remain attached to Morning.

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

Automated application and frontend checks are recorded in [VERIFICATION.md](VERIFICATION.md). The hosted database health check and private catalog configuration are complete. A real model reply from the hosted deployment, data recovery after a hosted restart, venue network rehearsal, and sustained AI capacity for 30 to 40 teams still need live checks. See [READINESS.md](READINESS.md) for the completion criteria. Free provider capacity can run out during a burst; a retryable AI error does not pause the event clock.
