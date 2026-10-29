# Remaining event preparation

Round one is five minutes with at most three attempts. A correct order earns 2 marks and opens round two immediately. Three unsuccessful attempts or expiry also opens round two. Each team then has fifteen minutes. Morning and Afternoon keep independent registrations, starts, results and exports.

The application records objective marks out of 6. Prompt quality remains pending until post-event review supplies up to 4 marks. Excel exports and validated grade imports are implemented. An automatic AI judging notebook is not implemented; the later scoring pass still needs the exported transcripts and organizer review.

## Before the event

| Work | Current state | Completion check |
| --- | --- | --- |
| Shared hosting | Source and Render Blueprint are ready; public deployment is unfinished | Render Free serves the actual HTTPS URL and health reports Postgres |
| Persistent database | Neon Free project was created; its application connection is unfinished | Register a rehearsal team, restart the service, and recover its access and marks |
| API capacity | A real Groq request succeeded; 40-team live AI throughput is unverified | Rehearse sustained prompt traffic within the account's actual quota |
| Optional Ollama backup | Real authenticated local reply succeeded; remote bridge is unfinished | Render reaches its HTTPS gateway, rejects missing credentials, and accepts a backup reply when Groq is unavailable |
| Competition puzzles | Twelve balanced private pairs are prepared locally and validated; they are not active | Review the private catalog and upload it as a Render Secret File before registration |
| Theme | All four pages use the reference theme; controller and static checks pass | Inspect laptop and narrow layouts, keyboard navigation, readable clocks and long messages in a real browser |
| Session rehearsal | Isolated tests cover Morning and Afternoon | Rehearse both sessions on the actual deployment without touching the clean competition database |
| Venue readiness | Not tested | Test the intended laptops and Wi-Fi, organizer login, both exports and provider failure behavior |
| Result retention | Excel export and local SQLite backup tools exist | Keep each session's private workbook and a database backup in organizer-controlled storage |

Free Groq limits and the single local Ollama gateway can still produce busy or retry errors during a burst. More API keys in the same organization do not increase its quota. A successful local 40-team database rehearsal does not prove live model capacity. Complete the actual provider rehearsal before declaring the event ready.

The private catalog is at `backend/private/competition-ciphers.json`, with an organizer-only guide beside it. Both files are ignored by Git. It uses twelve new pairs of six-letter words with Caesar and Atbash so teams face comparable operations. The public rehearsal catalog retains twelve pairs across six protocol types. Neither catalog guarantees identical difficulty for every word.

Set `CIPHER_CATALOG_PATH=/etc/secrets/ciphers.json` after adding the private JSON through Render Secret Files. Changing the catalog does not change puzzles already assigned to registered teams. Keep rehearsal and competition on separate database branches.

## Audit fixes

The audit fixed stale team-recovery and transcript responses, session export filenames, game startup responses, cross-tab team access changes, keyboard focus during round changes, narrow-table keyboard access and long heading wrapping.

Prompts now persist before the provider call. Interrupted and unexpected failures remain available in admin and Excel without counting as accepted turns. All workbook worksheets use one database snapshot, so a concurrent grade cannot produce contradictory totals and audit rows.

Database startup now checks the schema version and skips repeated schema changes when it is current. This fixes a deadlock found while two workers restarted together. The updated full suite passes 75 tests, including the real Postgres restart rehearsal.

The Ollama client rejects redirects. Ciphertext redaction handles additional numeric separators and compatible Unicode forms. Negated or quoted technique mentions no longer unlock a hint by themselves. Model output filters remain bounded checks; they cannot prove that arbitrary generated text never implies an answer or an unreleased operation.

Requests admitted before the deadline may finish afterward. Exports include submission and completion times. No late response can independently award decoding marks. Provider outages do not pause the server clock.

Optional per-criterion grading cells currently become a quality total and evidence reason during import. Preserve the completed judging workbook if the individual criterion values need to remain part of the organizer's record.
