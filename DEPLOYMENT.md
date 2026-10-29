# Free hosting with Render and Neon

Render Free hosts the Flask website and API. Neon Free stores registrations, sessions, transcripts, attempts, scores, reviews, and provider budgets. Teams and organizers use one HTTPS URL. No purchased domain, disk, or paid database is required.

Windows remains the local development environment. Render runs the hosted Python app on Linux with Gunicorn. Local Windows startup uses Waitress through `start_station.bat`.

## Deployment configuration

The source must be pushed to a GitHub repository that the organizer controls. The original is [dhanushnallam-25/Aarohan_2026](https://github.com/dhanushnallam-25/Aarohan_2026). The authorized deployment copy is [Akshitad23/Aarohan_2026](https://github.com/Akshitad23/Aarohan_2026).

The supplied `render.yaml` defines one Free Python web service in Singapore. It installs `backend/requirements.txt` and runs Gunicorn from `backend/`. It uses one process, eight threads, and at most four database connections. Automatic deployment is disabled so a source push cannot restart a running event.

Set these private environment variables in Render:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Neon pooled connection string, retaining SSL parameters |
| `REQUIRE_DATABASE_URL` | `true` |
| `ADMIN_PASSWORD` | A private organizer password |
| `GROQ_API_KEY` | The primary provider's private key |
| `PYTHON_VERSION` | `3.12.10` |

Set the health check to `/api/health` and verify `storage: postgres`. Hosted startup requires Postgres and cannot silently use Render's temporary filesystem. Provider configuration does not prove that an accepted live reply has succeeded.

The Neon project created for this event is `aarohan-2026`, ID `long-resonance-44700210`, in AWS Singapore on the Free plan. Its production branch is `br-lucky-tree-b3wq68cp`. Use a child branch for rehearsal and the clean production branch for competition. Use pooled connections for web traffic and direct connections for migrations or `pg_dump`. Never commit either connection string.

## Run both sessions

Morning and Afternoon have separate registrations, starts, deadlines, results, reviews, and exports. A team's access stays attached to its registered session.

1. Select Morning in admin and open its registration. Teams register and wait in the lobby.
2. Check the roster and start Morning once. All registered teams receive the same timeline deadline.
3. Round one allows five minutes and three attempts. Success earns 2 marks and opens round two immediately. Exhausted attempts or expiry opens round two with 0 timeline marks. Round two lasts fifteen minutes per team.
4. Each decoded word earns 2 marks. Prompt quality stays pending. Admin shows objective marks out of 6 until review supplies the remaining 4 marks.
5. End Morning and download its full Excel workbook.
6. Activate Afternoon registration and repeat. This preserves Morning.
7. Score each session separately after play. Follow [the scoring pipeline](docs/PROMPT_SCORING.md), validate the review file with a dry run, and apply it after checking the report. Results then show final marks out of 10.

Keep the same server for both sessions. There is no need to clear the database or create another deployment. Restarting reconnects to saved state.

## AI capacity and optional backup

Groq is always the first provider. Keys in one organization share its limits and do not add capacity. The application uses a shared database budget, compact context, per-team pacing, and provider cooldowns. See [Groq rate limits](https://console.groq.com/docs/rate-limits).

The defaults for `openai/gpt-oss-120b` are 30 requests per minute, 8,000 tokens per minute, 1,000 requests per day, and 200,000 tokens per day. Verify the actual account allowance before play. These defaults cannot guarantee an immediate generated reply to every prompt from 40 teams.

Ollama is an optional backup only when Groq cannot supply accepted output. Configure `OLLAMA_BACKUP_URL`, `OLLAMA_BACKUP_MODEL`, and `OLLAMA_BACKUP_TOKEN`. Render requires an authenticated HTTPS gateway. Its `localhost` cannot reach an organizer's Windows laptop. Follow [the backup setup](docs/OLLAMA_BACKUP.md).

If both providers fail, the student sees a retryable error and keeps the draft. The request is recorded for review. It does not create a substitute chat reply, count an accepted turn, or unlock a hint. The clock continues. Test the backup at the venue before relying on it.

Accepted exchanges record their provider. The server controls hints, answer validation, clocks, and marks. Model output cannot award points. Each word has three eligible techniques; one meaningful eligible prompt releases its protocol name, operation, and unrelated example together.

## Free-service limits

Render Free sleeps after 15 minutes without traffic. Open the app and admin before registration and verify both have woken before Start. Active gameplay polling supplies ordinary traffic. Neon can suspend idle compute; the bounded pool reconnects. Check actual allowances and status in both dashboards. Sources: [Render Free](https://render.com/docs/free), [Neon pricing](https://neon.com/pricing), [Neon pooling](https://neon.com/docs/connect/connection-pooling).

Render's filesystem is temporary. Keep state in Neon and download each session's workbook. Exports contain student details and full transcripts, so keep them private. A scoring workbook does not replace a database backup.

The built-in catalog and [cipher document](docs/CIPHERS.md) contain public rehearsal answers. For competition, add a fresh private catalog through Render Secret Files and set `CIPHER_CATALOG_PATH=/etc/secrets/ciphers.json`. Invalid catalogs stop startup. Use protocol pairs of comparable difficulty when ranking teams.

## Verify before admitting teams

Check registration, lobby, admin authentication, simultaneous start, all timeline outcomes, both word answers, accepted Groq output, quota-triggered backup output, full Excel export, separate Afternoon registration, and saved access after restart. Rehearse with 40 team browsers on the venue network. Local tests do not measure Render Free CPU limits, internet latency, or the actual provider allowance.

Keep rehearsal data on a child Neon branch. Never delete a competition database to reset the game. To preserve a local event, use `backend/backup_event.py`, then import into an empty target with `backend/migrate_sqlite.py`. The importer refuses to overwrite an event.

[The verification record](docs/VERIFICATION.md) distinguishes completed checks from cloud and venue checks that remain pending.

The latest audit and remaining release work are in [the readiness checklist](docs/READINESS.md). A private balanced competition catalog has been prepared locally under the ignored `backend/private/` folder. It has not been uploaded or activated.
