# AI: Think. Hack. Create.

For the complete setup, rehearsal, session, outage and grading procedures, use the [final event runbook](docs/FINAL_EVENT_RUNBOOK.md).

The application combines team registration, a two-part cryptography challenge, and an organiser dashboard. Flask serves the website and API from one origin. Test, Morning, and Afternoon have separate registrations, clocks, transcripts, attempts, and results. Test uses public rehearsal ciphers; it never receives the private competition catalog. Hosted deployments use Neon Postgres; local development can use SQLite.

## Event flow

1. Before the event, the organizer can select Test in `/admin` for a venue rehearsal. Test registrations and results are isolated from competition sessions and use the public rehearsal cipher catalog.
2. End Test, select Morning, and choose **Open registration for this session**. Morning teams then register and wait until the organizer starts that session.
3. Teams register at `/` and enter the waiting room. To move to another computer, generate a 5-character transfer code. It expires after 10 minutes and can be used once; using it moves the team's access to that computer.
4. The organizer starts the selected competition session for all its teams together.
5. Round 1: Part A lasts five minutes and permits three complete timeline submissions. A correct order earns 2 marks and opens Round 1: Part B immediately. Three unsuccessful submissions or expiry also open Round 1: Part B, with 0 timeline marks.
6. Each team has fifteen minutes in Round 1: Part B by default. Students prompt CHRONOS for two independent cipher hints, decode the words themselves, and submit each answer separately. Each correct word earns 2 marks.
7. The live dashboard shows objective marks out of 6. Prompt quality and the final score remain pending until organizers grade the transcript after the session ends.
8. End Morning before opening Afternoon registration. A team's browser access stays with its original session. Students joining Afternoon need a new registration. Transfer codes move access between computers, expire after 10 minutes, and work once.

The server controls deadlines, attempts, hint release, and scoring. Refreshing the page does not reset progress or pause time. The dashboard polls every three seconds. Game polling requests only new transcript entries and pauses while the tab is hidden; server clocks continue running.

## Cipher hints and AI dialogue

Each word has three eligible prompting techniques. One meaningful prompt using any one of its three techniques releases the complete hint pack: protocol name, concept, decoding operation, key where needed, and an unrelated worked example. Students still submit the decoded word themselves. There is no requirement to succeed with two techniques or complete several study turns first.

The technique pool includes instruction override, roleplay, task decomposition, authority framing, fiction, and hypothesis testing. The server validates the selected target and the actual request. A bare keyword does not unlock a hint. See [the challenge rules and examples](docs/AI_RECOMMENDATIONS.md).

Groq is the primary model provider. A configured Ollama model is the backup when the primary call is unavailable or its output fails validation. Both generate real dialogue from redacted context. The server supplies only the hint information approved for release and keeps the assigned answers out of model context.

If neither provider can answer, the API returns a retryable error. It does not invent a response or substitute a canned hint. The student's prompt stays in the input, and the failed request is logged for organizers. Failed requests do not consume accepted turns, release hints, or award marks. Time limits continue.

Provider limits apply across the organization. The shared request and token budget coordinates workers, applies cooldowns, and favors waiting teams. Extra keys in the same organization do not add capacity. Free capacity cannot guarantee a primary-model reply for every prompt from 40 teams. The dashboard distinguishes configured providers from verified replies and shows API budget remaining. For backup connectivity, see [the Ollama setup instructions](docs/AI_RECOMMENDATIONS.md#configuring-ollama-backup).

## Scores and post-event grading

| Component | Maximum |
| --- | ---: |
| Timeline | 2 |
| First decoded word | 2 |
| Second decoded word | 2 |
| Prompt quality, graded after the session | 4 |
| Final total after grading | 10 |

There are no automatic prompt-quality marks, time bonuses, prompt-count penalties, or hint deductions. Until a judge records quality marks, the objective score is out of 6 and the final score out of 10 is empty.

Select the session in the admin dashboard and use **Export Excel** to download its workbook. It includes registrations and participants, accepted prompts and responses, failed AI requests and provider details, recorded timeline submissions and word guesses, score summaries, an editable `QualityReview` sheet, and the review audit history. Access codes are excluded.

After the session ends, grade each transcript in the dashboard or fill `QualityReview`. Keep `batch_id` and `team_id` unchanged. Enter either a score from 0 to 4 with a reason, or all four rubric values from 0 to 1 with a reason. Use numeric values rather than formulas. The [grading procedure](docs/PROMPT_SCORING.md) explains the rubric, workbook, CSV format, and audit trail.

To validate and then import a completed workbook from the repository folder:

```powershell
.\.venv\Scripts\python.exe backend\grade_reviews.py .\aarohan-morning-results.xlsx
.\.venv\Scripts\python.exe backend\grade_reviews.py .\aarohan-morning-results.xlsx --apply
```

Configure the intended event database before importing. The first command makes no grade changes. `--apply` validates all completed rows, then saves them in one transaction. It rejects wrong session/team combinations and sessions that have not ended. Download a fresh workbook after grading to capture final results.

## Local setup on Windows

Use Python 3.12. For the first setup, run these commands in PowerShell from this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Set `ADMIN_PASSWORD` and `GROQ_API_KEY` in `backend/.env`. Configure Ollama backup if required. The admin username is `admin`; there is no built-in password. With neither provider available, chat requests return an error.

Run `start_station.bat`. It starts Waitress on Windows. Keep the server window open. Team registration is at `http://localhost:5000/`, and organizer login is at `http://localhost:5000/admin-login`. Other laptops need the shared server's address or hosted URL, rather than their own localhost address.

## Hosting on Render

The supplied Blueprint targets Render Free with Neon Free and creates no paid disk or database service. Configure a private Neon pooled `DATABASE_URL`, admin password, and provider credentials in Render. Hosted startup refuses SQLite fallback so a redeploy cannot silently replace persistent event data with an ephemeral database.

If Render is unavailable, the organizer can start the Windows laptop fallback against the same Neon database. Prepare the private credentials, catalog and Ollama model before event day; follow [the Windows fallback runbook](docs/WINDOWS_FALLBACK.md).

Linux hosting uses Gunicorn. From `backend/`, its start command is:

```bash
gunicorn --config gunicorn.conf.py app:app
```

A local Ollama address on an organizer's laptop is not reachable through Render's localhost. A hosted backup needs a reachable authenticated HTTPS gateway, a running model, and a stable connection. Follow [deployment and event operations](DEPLOYMENT.md) for account setup, the public URL, environment variables, backups, and live checks.

The built-in cipher catalog is public rehearsal data. Prepare a fresh private competition catalog using [the catalog format](docs/CIPHERS.md).

## Verification

From the repository folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tests\rehearse_event.py --teams 40
node tests\frontend_smoke.cjs
```

The frontend smoke test exercises the actual page controllers with a small test DOM. It checks pending and reviewed scores, provider-error draft retention, API and Ollama labels, Morning/Afternoon registration, historical results, failed request visibility, and the selected-session Excel export.

The HTTP rehearsal uses its own server and temporary database. Provider calls are isolated from real credentials. Postgres tests require `PG_ADMIN_TEST_URL` for a local test role with `CREATEDB`; they reject remote hosts and create their own temporary databases. GitHub Actions supplies a disposable Postgres service and runs the Python checks, rehearsal, JavaScript syntax checks, and frontend smoke test.

Local tests do not certify cloud or provider capacity. Use [the verification record](docs/VERIFICATION.md) and complete the live deployment checks before admitting students.

## Project documents

- [Implementation plan and original issues](docs/IMPLEMENTATION_PLAN.md)
- [AI behavior, technique examples, and backup setup](docs/AI_RECOMMENDATIONS.md)
- [Cipher combinations and private catalog format](docs/CIPHERS.md)
- [Post-event grading and export/import pipeline](docs/PROMPT_SCORING.md)
- [Event operator guide](docs/EVENT_OPERATOR_GUIDE.md)
- [Deployment and event operations](DEPLOYMENT.md)
- [Verification record](docs/VERIFICATION.md)
- [Remaining event preparation](docs/READINESS.md)
