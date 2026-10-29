# Event implementation plan

The target is 30 to 40 teams using one shared website. Morning and Afternoon have separate registrations, clocks, logs, and results. Each team registers for the active session, waits for its organizer start, and completes both rounds. The live score covers objective marks out of 6; prompt quality and the final total out of 10 remain pending until post-event grading. The same server supplies the admin dashboard.

## Findings in the original repository

| Problem | Effect | Change |
| --- | --- | --- |
| Browser includes answers, order, an offline engine, and independent scoring | Network failure can create a local game that never reaches the admin dashboard; students can inspect answers | Remove the offline engine and keep decisions on the server |
| AI supplies a very short atmosphere line; most responses come from rules | Chat can appear unresponsive or repetitive even with a provider key | Use bounded real provider calls, a real Ollama backup, and server-approved hint release; report an error if neither provider answers |
| Multiple legacy password and timeline game routes coexist | Conflicting rules, scores, and frontend assumptions | Use one active two-word event flow |
| Sessions live in process memory | Restart loses progress; different workers see different sessions | Persist sessions in Neon Postgres for hosting, with SQLite for local work |
| Admin password is published and checked in frontend code | Anyone can impersonate an organizer | Server authentication with expiring private tokens; no supplied production password |
| A team name selects a session | Another laptop can act as that team | Issue a private team token on registration |
| One fixed cipher pair and stale Caesar instructions | Hints and scoring describe different puzzles | Store validated cipher variants on the server |
| Scores use several incompatible scales | Admin totals do not match the event rules | One score calculation, maximum 10 |
| No global event start | Teams start at different times | Persistent event start time and a waiting lobby |
| Free hosting configuration stores logs on ephemeral disk | Deploy or restart can erase event records | Render Free with persistent data in Neon Free |

The Kalakriti project was inspected as requested. Its useful pattern is to decide unlocks on the server and keep answers out of model context. Its deployment notes also document in-memory sessions, a serial worker, and browser-controlled rules. Those limitations should not be copied into this event.

## Delivery sequence

1. Separate cipher data, hint unlock rules, and provider dialogue. Validate every cipher round trip. Each word accepts any one of three eligible meaningful techniques and releases its full hint pack at once.
2. Make registration, event state, sessions, transcripts, attempts, scores, and admin review persistent. Authenticate every team mutation. Reserve a prompt before the provider call, then save its result without holding a database write lock during the network request.
3. Replace the client-side simulation with same-origin API requests. Restore sessions after reload and show a connection error when the server is unavailable.
4. Add separate Morning and Afternoon registrations and organizer start/end actions, with a shared round-one deadline inside each session. A correct answer advances immediately. Three unsuccessful submissions or expiry also advance to round two.
5. Score timeline accuracy out of 2, each decoded word out of 2, and prompt quality out of 4. Show objective marks out of 6 while leaving quality and the final score pending. Grade the transcript only after its event session ends.
6. Add the session-filtered admin roster, score updates, complete transcripts including failed AI requests, Excel exports, and audited post-event grading. Poll every few seconds; this is near-real-time polling, not a push connection.
7. Test invalid access, duplicated requests, refresh/restart recovery, timeout boundaries, scoring, cipher correctness, provider failure, and concurrent teams. Run a 40-team rehearsal on an isolated database.
8. Prepare deployment with a persistent database, concurrent workers, health checks, environment-only secrets, backups, and disabled automatic deployments during the event.

## Free hosting revision

The organizer chose a zero-cost deployment. The active Blueprint now uses Render Free and an external Neon Free database, with no paid disk. `DATABASE_URL` takes precedence over local SQLite, and Render refuses startup without it. Database initialization and mutations coordinate across processes. A verified importer can preserve an existing current-schema SQLite event in an empty Postgres destination.

Groq uses one shared organization budget stored in the database. Extra keys within that organization do not add allowance. Request and estimated token reservations, actual usage reconciliation, provider cooldowns and expiring waiting tickets survive application restarts. Requests without primary capacity try the configured real Ollama backup. If both providers are unavailable or fail output validation, the API returns an explicit retryable error and preserves the prompt draft. That failed request is logged but cannot release a hint or consume an accepted turn. Free capacity does not promise continuous live dialogue for all 40 teams.

Incremental transcripts reduce both Neon-to-server and server-to-browser transfer. Hidden and finished browser pages poll less often. The verification record tracks the tested version and rehearsals. Live hosting, provider credentials, and backup connectivity need separate verification.

## Rules used where the request leaves a choice

- Round one starts at the admin's shared event start, lasts 300 seconds, and permits at most three complete submissions. A correct timeline earns 2 on any permitted attempt. There is no speed or attempt penalty.
- Each team gets 900 seconds for round two from the time it advances. The request permits early progression, so a team that solves round one early can finish earlier. All teams receive the same round-two duration. Both sessions use this same timing rule.
- Teams can reach round two even with 0 in round one.
- Decoding earns marks only through the separate answer submission fields. A chatbot response cannot award decoding marks.
- Automatic prompt-quality marks are removed. After its event session ends, a judge reviews the full transcript and records a score with a reason. The Excel grading template can be validated and imported atomically through grade_reviews.py.
- No time bonus, prompt-count penalty, or hint deduction is included in the total of 10.

## Release conditions

Local tests do not establish cloud capacity or live provider availability. Before admitting students, deploy the exact tested version, check live model responses, rehearse with the intended laptops and network, verify provider quotas, check admin exports and backups, and verify the eligible techniques and calibrate the quality rubric. Use a separate rehearsal database so the competition starts with an empty lobby.

A public URL requires a hosting account and deployment of these local changes. No public URL should be presented as live until its deployment and end-to-end checks succeed.
