# AI: Think. Hack. Create. event runbook

This is the main operations guide for the organizer. It covers local rehearsal, the hosted event, both sessions, the Windows fallback, and recovery from AI or hosting failures. Keep competition answers, team data, access codes and environment files private.

## 1. One-time setup

The public event runs from Render and stores state in Neon Postgres. The deployed site is [ai-think-hack-create.onrender.com](https://ai-think-hack-create.onrender.com). The Windows laptop fallback is already prepared in this checkout. The production secrets are in the ignored file `backend/.env.event`; the private cipher catalog is in the ignored folder `backend/private/`. Do not commit or send either one.

The fallback launcher uses the same Neon production database as Render. It checks the database and catalog before it starts and refuses to silently use SQLite. Keep this project folder, `.venv`, `backend/.env.event`, and the private catalog on the organizer laptop. Keep the laptop plugged in and prevent it from sleeping during both sessions.

Ollama and `gemma3:4b` are installed on the organizer laptop only. That laptop runs both the website and the model during fallback. Participant machines need only a web browser; they connect to the laptop over venue Wi-Fi and send their prompts to its local app. They do not install Ollama. Render cannot reach Ollama at the laptop's `127.0.0.1`, so if Groq is unavailable while using Render, move all teams and the admin to the laptop-hosted site. A direct model response and the app's Groq-to-Ollama fallback path were tested. Test the laptop's Wi-Fi address from another device at the venue before event day.

## 2. Rehearse admin and participant flows safely

Use a local SQLite rehearsal database for development tests. It is separate from the Neon event database. For hosted multi-computer checks, use the dedicated Pre-test session. Never add fake teams to Morning or Afternoon; they would appear in competition rosters and exports.

From PowerShell at the project root, prepare the local rehearsal config once:

```powershell
if (-not (Test-Path backend\.env)) { Copy-Item backend\rehearsal.env.example backend\.env }
```

If `backend\.env` already exists, do not overwrite it; confirm it has rehearsal-only settings first. Set a rehearsal-only `ADMIN_PASSWORD`. Leave `DATABASE_URL` blank and `REQUIRE_DATABASE_URL=false`. Leave `GROQ_API_KEY` blank to exercise the local Ollama backup without using Groq quota. If Ollama is not installed on the rehearsal laptop, install and warm `gemma3:4b` first or enter a valid Groq key instead.

Start the local site:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Then run `start_station.bat` and leave its terminal open. It uses the isolated `backend/data/rehearsal.sqlite3` database.

### Organizer test

1. Open `http://localhost:5000/admin-login` and sign in as `admin` using the rehearsal password.
2. Open the admin dashboard. Select **Morning**, open registration, and confirm the session is waiting for teams.
3. Register one fake team from a second browser or an InPrivate window. Use clearly fake names such as `Rehearsal Team` and `Test Student`; do not enter real participant data.
4. Confirm the new team and its status appear in the admin roster. Start Morning once.
5. Check that the dashboard reports the live phase and objective score. The dashboard refreshes while the game clock remains server-controlled.
6. End the rehearsal session, export its Excel workbook, and confirm its team and transcript appear. Test quality grading only in this local database.

### Participant test

Use a separate browser profile or device and open `http://localhost:5000/`. Register the fake team for Morning and save its resume code for this rehearsal. Confirm it reaches the waiting room. After the organizer starts Morning:

1. Try the event timeline. It allows five minutes and up to three submissions. A correct order earns 2 marks and opens Part B immediately; three unsuccessful submissions also open Part B, with no timeline marks.
2. In Part B, send a meaningful prompt about one target word using one technique from [AI behavior and example prompts](AI_RECOMMENDATIONS.md). The assigned eligible techniques vary, so try another technique if the first prompt does not release that word's hint.
3. Confirm the released pack contains the protocol name, operation, and example. Decode and submit the word. Repeat for the second word. Each correct answer earns 2 marks.
4. Confirm the participant sees the score and can resume from the same browser profile. Generate a transfer code, enter it once on another browser or computer, and confirm the team continues there. The code expires after 10 minutes and moves access to the new computer. The objective score is out of 6; prompt quality remains pending until organizer review adds up to 4.

Use **Afternoon** in the local rehearsal only if you also want to verify session separation. It has separate registration, start state, results and export. Never use these rehearsal steps on the public competition batch.

The configured local AI uses Ollama when Groq is blank. To test the Groq path locally, add a valid, organizer-authorized key to the rehearsal `.env`; this consumes that organization's quota. Do not cycle accounts or keys to evade a quota.

## 3. Before each event session

### Pre-test now with any computers

Use Pre-test for an early end-to-end trial from home, campus or another location. Use the hosted site or the prepared laptop app and keep all devices on the same URL. Pre-test has its own registrations and results and uses public practice ciphers, never the private competition catalog.

1. Sign in on the admin computer, select **Pre-test**, and click **Open registration for this session**.
2. On as many participant computers as you want, open the team page and register clearly fake practice teams. Do not enter real participant details.
3. Confirm all practice teams appear in the Pre-test roster. Click **Start Pre-test for all teams** once. Confirm each computer enters Round 1: Part A.
4. Check the timeline, chatbot replies, both cipher hints, answer submissions, and transfer-code flow. If testing transfer, generate a code on one participant computer and redeem it on another.
5. When finished, select **Pre-test** and click **End Pre-test**. It is closed permanently; its records stay under Pre-test and do not affect Test or competition scores.
6. Leave Morning unopened. Before the event, use the separate Test session for the venue computers.

### Test at the venue before Morning

Use the Render site or the prepared laptop-hosted app, but keep everyone on one URL throughout the venue check. Test is a separate session from Pre-test and uses the public rehearsal ciphers, not the private competition catalog.

1. On the admin laptop, sign in and select **Test** in the session dropdown. Click **Open registration for this session**.
2. On the two venue computers, open the team page and register two clearly fake teams, such as `VENUE TEST A` and `VENUE TEST B`. Do not use real student details.
3. Confirm both teams appear in the Test roster. Click **Start Test for all teams** once. Confirm both computers leave the waiting room and begin Round 1: Part A.
4. From the team computers, check the timeline, Part B, chatbot response, answer submission and transfer code. Test hints use only the public rehearsal puzzles, so they do not reveal competition answers.
5. When satisfied, select **Test** in admin and click **End Test**. Test is closed and cannot be reopened. Its teams, prompts, scores and export remain under Test, separate from Morning and Afternoon.
6. Select **Morning** and click **Open registration for this session**. Confirm admin and the registration page show **Morning / Waiting for teams** before inviting competitors.
7. Participant browsers that registered a Test team keep that private Test code in local storage. In the same browser, register the real Morning team using its own details; the site will warn that this replaces the saved Test access. Or open a clean InPrivate profile. Do not resume a Test code as a Morning team.
8. Confirm the Morning roster contains only competition teams. Start Morning once all teams are ready.

If the venue test fails, do not start Morning. Check the admin error, public health page, Wi-Fi and laptop fallback first. If Test has already ended, fix the issue and rehearse on the isolated local SQLite setup in section 2; do not try to reopen Test on the competition database.

### Checks before Morning and Afternoon

Do these checks before Morning, then repeat the service and roster checks before Afternoon:

1. In Render, confirm the service is live. Open `https://ai-think-hack-create.onrender.com/api/health` and verify `status: ok` and `storage: postgres`. If the page is waking from sleep, allow about a minute.
2. Sign in at `https://ai-think-hack-create.onrender.com/admin-login`. Confirm the correct session is selected and check provider configuration and remaining budget.
3. Use Pre-test for a hosted end-to-end check, including an actual Groq response. Test and Pre-test rosters are separate from competition teams. Do not create fake teams in Morning or Afternoon.
4. Confirm the private competition catalog is active. It is stored in Render's masked `CIPHER_CATALOG_JSON` setting and the local private file. Never show the catalog to students or put it in Git.
5. Confirm the organizer laptop has power, `backend/.env.event`, the private catalog, Ollama and `gemma3:4b`. The laptop fallback preflight should pass. Test `start_event_fallback.bat` from a second device on the same Wi-Fi before participants arrive, then close the rehearsal server.
6. Check the actual Groq organization limits in its console. Groq limits apply at the organization level. Its policy prohibits registering multiple accounts or orchestrating organizations to get around limits. Do not rotate through accounts to bypass 429s. The app is paced for the configured budget and the laptop has local Ollama backup. See [Groq's rate limits](https://console.groq.com/docs/rate-limits) and [acceptable-use policy](https://console.groq.com/docs/legal/ai-policy).
7. Check that the organizer has a private destination for two Excel exports, one per session. Exports contain participant information and full prompts.
8. For Afternoon, select it only after Morning is ended and exported, then click **Open registration for this session**. Check the roster as teams join. Start once, after the teams for that session are ready.

## 4. Session procedure and marks

Each session has a total of 10 marks:

| Component | Marks | When awarded |
| --- | ---: | --- |
| Timeline order | 2 | Correct event order within five minutes and at most three attempts |
| First word | 2 | Correct first decoded word |
| Second word | 2 | Correct second decoded word |
| Prompt quality | 4 | Organizer review after that session ends |

Part A is five minutes. A correct timeline lets that team move to Part B immediately. Three failed attempts or the deadline also lets them continue, with zero timeline marks. Part B is 15 minutes for each team from the time it enters that part. The server clock continues if a tab is refreshed, closed, or disconnected.

Prompt quality is not scored by the chatbot. After the session ends, review the transcript for clear task, relevant context, useful constraint or format, and testing or refinement. Each criterion is 0, 0.5 or 1. Two organizers should calibrate on the same rehearsal transcript. See [the scoring rubric and Excel workflow](PROMPT_SCORING.md).

To run Afternoon, end Morning and export it first. Then select Afternoon, open its registration, and start it once all Afternoon teams are ready. Do not clear or reset the database between sessions.

## 5. When and how to switch to the laptop

Use the Windows fallback if the public site remains unavailable for more than two minutes, or if Groq is unavailable and students are receiving chatbot errors. Do not switch just because `ai_live_verified` is false immediately after a restart; that field reports whether this running process has seen a successful reply yet.

1. On the organizer laptop, run `start_event_fallback.bat`. It performs a read-only database check and confirms Neon and the private catalog before serving pages.
2. Run `ipconfig`. Find the laptop's IPv4 address on the venue Wi-Fi network.
3. Tell every team and the admin to use the same URLs: `http://<laptop-IPv4>:5000/` for teams and `http://<laptop-IPv4>:5000/admin-login` for the organizer. If a team changes computers, generate a 5-character transfer code from its saved team page or ask the organizer to issue one in admin. It expires after 10 minutes and can be used once. Redeeming it moves the team's access to the new computer and signs out the old one.
4. If Windows Firewall prompts, allow Python on **Private networks only**. Keep the laptop awake and the launcher terminal open.
5. Keep everyone on the laptop URL for the rest of that session, even if Render returns. Both app instances write to Neon, but everyone should use one URL to avoid confusion.

### Provider and database failures

- **Groq returns an authentication error:** the key may be invalid or revoked. Replace it with a valid authorized key. Updating Render settings can restart the service, so do not rotate it casually during a live session. On the laptop, local Ollama is already available.
- **Groq returns 429, quota exhaustion, or a provider outage:** a new key from the same organization will not increase its organization limit. Do not rotate accounts to bypass the limit. Switch all teams to the organizer laptop-hosted site; that app can answer with the laptop's `gemma3:4b` model after Groq fails. Student devices need only a browser and access to the laptop's Wi-Fi address.
- **Both Groq and Ollama fail:** tell teams to stop submitting prompts and notify the organizer. The current app has no global pause control, so the Part B clock continues. If model recovery is not immediate, stop the session operationally and record the outage and affected teams; decide a fair continuation with the event lead.
- **Neon is unavailable:** neither Render nor the laptop can save shared progress. Stop play and record unfinished work offline. Do not start SQLite as a substitute during competition; that would split the teams and scores into a separate database.
- **Venue internet is lost:** the laptop Ollama can still generate text, but the shared Neon database requires internet. Without Neon, the app cannot safely continue the event.

## 6. After each session

1. End the session in admin.
2. Select that session and download **Export Excel**. Store the workbook privately; keep Morning and Afternoon exports separate.
3. Review prompt transcripts and award up to 4 quality marks per team. Save a reason that cites prompt turn numbers or short evidence.
4. If grading in Excel, keep `batch_id` and `team_id` unchanged. Validate the workbook before applying it, then download a fresh copy with final scores and review audit history. The steps are in [the scoring guide](PROMPT_SCORING.md).
5. Before opening Afternoon, confirm Morning's export is saved.

## 7. Files and links

- [Windows fallback setup and troubleshooting](WINDOWS_FALLBACK.md)
- [Operator guide](EVENT_OPERATOR_GUIDE.md)
- [Prompt-quality scoring](PROMPT_SCORING.md)
- [Cipher catalog rules](CIPHERS.md)
- [Readiness checklist](READINESS.md)
- [Verification record](VERIFICATION.md)
- [Hosted team site](https://ai-think-hack-create.onrender.com/)
- [Hosted admin login](https://ai-think-hack-create.onrender.com/admin-login)
- [Hosted health check](https://ai-think-hack-create.onrender.com/api/health)

## Participant display and prompt routing

Teams see correct or incorrect submissions, timers, prompts and unlocked hints. Scores and prompt-quality grades are available only to organizers in admin and exports. There is no word selector in chat. The server checks each meaningful prompt against the techniques assigned to both words and labels released hints with the associated word number. A prompt can unlock both words if it matches both groups.

Completed teams are automatically signed out of the participant browser. Returning to registration shows a fresh form. Team records and transcripts remain in admin. Before reusing a computer, wait for the thank-you screen.
