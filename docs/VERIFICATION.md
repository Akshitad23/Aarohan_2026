# Verification record

Checked on 30 October 2026 using Windows and Ubuntu under WSL. Automated tests use temporary databases and disabled or mocked provider calls. The Kalakriti reference was inspected without modifying it.

## Current automated checks

The recorded Linux run passed 77 Python tests on Python 3.12 with PostgreSQL 16, Gunicorn 23, psycopg 3.3.6 and openpyxl 3.1.5. The current Windows run passed 73 tests and skipped five optional local-Postgres tests. It includes a check for loading the private catalog from Render's masked environment variable. The frontend smoke test, JavaScript syntax check and `git diff --check` also pass.

The audit added checks for durable prompts after unexpected errors and interrupted workers, consistent workbook snapshots during concurrent grading, quoted and negated technique mentions, numeric and Unicode redaction, and rejected backup redirects. A real Postgres restart deadlock was reproduced and fixed. Current schema versions skip repeated startup changes; a regression checks initialization while another connection holds a read transaction.

GitHub Actions also exposed a simultaneous SQLite journal-initialization race. Initialization now retries only SQLite BUSY and LOCKED errors within a five-second budget. Read-only, corrupt and unclassified errors still fail immediately. Parallel startup checks passed four fresh-database trials with four simultaneous processes on both Windows and Linux.

Coverage includes independent Morning and Afternoon registration and clocks, immutable team access, legacy-schema migration, objective marks out of 6, pending quality, audited post-event grading, atomic CSV/XLSX grade imports, and full workbook exports. Exports preserve long text in continuation columns and prevent text from becoming executable spreadsheet formulas.

All 12 cipher combinations round-trip. Each of the 72 eligible word/technique paths releases the entire hint after one meaningful prompt. Bare keywords and requests for plaintext do not unlock hints. Provider tests cover Groq priority, optional Ollama backup, output checks, quota admission across processes, and explicit failures without accepted turns or clue progression.

The gateway's eight focused tests cover authentication, its fixed local upstream, pinned model, bounded context and output, concurrency, invalid requests, and upstream errors.

JavaScript syntax and `node tests/frontend_smoke.cjs` pass. The checks cover 5-minute and 15-minute clocks, three timeline attempts, immediate progression, session selection, draft retention, provider identity, pending and reviewed marks, transcripts, and Excel downloads. Deferred-response tests cover team recovery, export filenames, initial state loading and cross-tab access changes. Phase changes focus the new heading while same-phase polls preserve focus. All four pages have unique IDs and existing assets. The audit revision passed [GitHub Actions](https://github.com/Akshitad23/Aarohan_2026/actions/runs/40934038573), including all Python tests, a separate 40-team rehearsal, JavaScript syntax and frontend controller checks.

## Forty-team rehearsal

The latest full suite launched two Gunicorn processes with eight threads each against one disposable Postgres database. Both processes were restarted before checking saved access and results.

| Measurement | Result |
| --- | ---: |
| Teams | 40 |
| HTTP requests | 382 |
| Unexpected failures | 0 |
| Median response | 78.7 ms |
| 95th percentile | 440.6 ms |
| Maximum | 539.8 ms |

The rehearsal covers concurrent registration, shared start, immediate timeline success, exhausted attempts, separate word marks, AI failure telemetry, pending quality, post-event review, independent Afternoon registration, logout, and restart recovery. Provider calls are disabled in this test. These measurements do not establish Render Free capacity, Neon internet latency, venue connectivity, or live AI throughput.

## Real provider check

The new Groq key returned an accepted reply through the actual game engine in an isolated temporary database. One eligible decomposition prompt unlocked the full first-word hint. The request took 1.12 seconds. This proves that one accepted provider request worked; it does not establish free quota capacity for 40 teams.

The real local Ollama path also passed with the installed `gemma3:4b` model and a temporary authenticated gateway. With Groq disabled only in that isolated test process, the engine accepted the backup reply and released the full hint in 8.95 seconds. The gateway was closed afterward. Its authenticated cloud tunnel remains unconfigured; local success does not prove that Render can reach the laptop.

## Theme and hosting

All four pages use the reference site's blue grid, cream paper, navy text, condensed headings and locally hosted font files. Browser review covered registration, admin login, dashboard, waiting room, timeline and prompt-engineering screens. User-visible event naming and round labels were corrected without a layout redesign. A whitespace-only dynamic status message that left an empty bordered box was removed. Keyboard navigation and multiple screen sizes still need a venue-device check.

The implementation is in [the authorized GitHub deployment copy](https://github.com/Akshitad23/Aarohan_2026). The Render Free service at [ai-think-hack-create.onrender.com](https://ai-think-hack-create.onrender.com) uses the Neon Postgres project and returns healthy status. A private competition catalog is configured through Render's masked environment variable; its JSON stays out of Git. The live AI health status shows configured credentials but no hosted provider reply yet. Cloud restart recovery and venue rehearsal remain unverified.

Twelve new private pairs use equal word lengths and the same protocol pair for more comparable ranked play. The public source catalog contains rehearsal answers. See [remaining event preparation](READINESS.md) before opening registration.
