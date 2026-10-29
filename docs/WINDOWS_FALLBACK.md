# Windows laptop fallback

Use this when Render is unavailable or when Groq is failing and you need the local Ollama model. Ollama runs only on the organizer laptop; the laptop serves both the website and model. Students need only a browser and venue Wi-Fi access to the laptop's address. Render cannot reach Ollama on the laptop through `127.0.0.1`. The organizer laptop connects to the same Neon production database, preserving teams' existing progress. A local SQLite database is not a valid fallback.

## Prepare before event day

1. Install Python 3.12 and Ollama on the organizer laptop. Pull and test `gemma3:4b`. Keep several GB of free disk space and make sure the machine can run the model.
2. Install the application requirements once:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   ```

3. Copy `backend\event-fallback.example` to `backend\.env.event`.
4. Fill the private values in `backend\.env.event` from Render's Environment page: use the same production Neon pooled `DATABASE_URL`, `ADMIN_PASSWORD`, and `GROQ_API_KEY`. Keep the file local and private. Do not commit it or send it in chat.
5. Set `CIPHER_CATALOG_PATH` to the full path to `backend\private\competition-ciphers.json`. Copy that ignored private file securely to the laptop if it is not already there.
6. Keep `REQUIRE_DATABASE_URL=true`. The fallback launcher checks the Neon URL, catalog, required credentials, and a live database connection before it starts. It exits instead of silently starting against SQLite.
7. Confirm that Ollama is running and lists `gemma3:4b`. The template points the local app at Ollama on `127.0.0.1:11434`, so it can provide backup replies when Groq is unavailable. A fresh model may be slow; warm it with an unrelated test prompt before event day.
8. Run `start_event_fallback.bat` and verify the team page, admin login, AI reply and shared production session from a second device. End any test session and export/delete the test records according to the event's data-retention plan. Do not rehearse on event day after registration opens.

## Switch during an outage

1. Check the public health page. If it is still unavailable after two minutes, use the organizer laptop. Connect it to power and keep it awake.
2. Run `start_event_fallback.bat` and leave the command window open. It performs a read-only Neon connection check and validates the private catalog before launching Waitress.
3. Run `ipconfig` and find the laptop's IPv4 address for the venue Wi-Fi adapter. Share `http://<IPv4-address>:5000/` with all teams and `http://<IPv4-address>:5000/admin-login` with the organizer. Everyone must use the same address. Teams may need to reopen the site and resume with their team code.
4. If Windows Firewall asks, allow Python on **Private networks only**. Never expose port 5000 on a public network.
5. Keep all teams on the laptop URL for that session, even if Render returns. The laptop app and Render both use Neon, but switching repeatedly risks sending participants to different experiences. After the session, export the results as usual.

## Diagnose chatbot failures

- An invalid or revoked Groq key: replace it with a valid key. Updating Render environment variables can restart the service, so do not rotate a key during play unless the provider confirms it is invalid.
- A Groq `429` or exhausted organization quota: another key in that same organization will not add quota. On the laptop fallback, the app tries local Ollama after Groq fails.
- A wider Groq outage: stay on the laptop fallback and use the tested local Ollama model.
- Ollama is also unavailable or too slow: stop new prompts and tell the organizer. The game clock continues; the app has no global pause control.
- Neon is unreachable: the laptop cannot safely continue the shared event. Stop play, record unfinished work offline, and resume only after Neon is back. Do not start SQLite.

For the event's full start, session and export procedures, see [the operator guide](EVENT_OPERATOR_GUIDE.md). For model setup and output limits, see [the Ollama backup guide](OLLAMA_BACKUP.md).
