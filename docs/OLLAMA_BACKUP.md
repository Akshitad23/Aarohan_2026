# Running the optional Ollama backup

Groq remains the primary provider. The application tries Ollama only when the primary request cannot produce an accepted reply. If both providers fail, students see a retryable error and keep their prompt. No canned response, hint, accepted turn, or prompt-quality mark is created.

The backup is not connected by default. It needs an organizer's running Ollama model and an authenticated HTTPS connection that Render can reach. Render cannot use `localhost` to contact a laptop.

## Start the gateway on Windows

Use the existing project Python environment and installed backend requirements. Ollama must already be running locally with the intended model installed. This setup does not download a model or choose one for your hardware.

Set these values in the gateway terminal. Use a private randomly generated token of at least 32 ASCII characters. Keep the same token in Render's secret environment settings; do not commit it.

```powershell
$env:OLLAMA_BACKUP_MODEL = '<your-installed-model-tag>'
$env:OLLAMA_BACKUP_TOKEN = '<your-private-gateway-token>'
python backend/ollama_gateway.py
```

The gateway listens only on `127.0.0.1:11435`. It forwards requests only to `http://127.0.0.1:11434/api/chat`, pins the configured model, and never forwards the gateway bearer token to Ollama. It accepts one active generation at a time. Other requests receive a short retry response instead of waiting in a queue.

Requests require `Authorization: Bearer <token>`. The gateway accepts only non-streaming text chat, two to six messages, at most 2,800 UTF-8 bytes of message content, a 4,096-token context setting, and at most 256 generated tokens. It rejects arbitrary URLs, model changes, unsupported options, large responses, partial responses, and upstream redirects. The main application still applies its secret-word and locked-protocol output checks to backup replies.

## Connect Render

Use a secure HTTPS tunnel that forwards to `http://127.0.0.1:11435`. Keep the gateway itself bound to loopback. This repository does not create a tunnel or make an organizer's laptop publicly reachable.

Set the following secret environment values on Render:

```dotenv
OLLAMA_BACKUP_URL=https://your-authenticated-tunnel.example
OLLAMA_BACKUP_MODEL=your-installed-model-tag
OLLAMA_BACKUP_TOKEN=the-same-private-gateway-token
OLLAMA_BACKUP_TIMEOUT=10
```

The URL can be the gateway base URL or the full `/api/chat` endpoint. Remote URLs require HTTPS and a bearer token. Loopback backup URLs are rejected when the app runs on Render. The model must match the gateway's pinned model exactly.

Keep the laptop awake, Ollama running, the gateway terminal open, and the tunnel connected for the event. A cold or slow model can exceed the request timeout. Test a warm model on the actual hardware and venue connection before relying on the backup. The gateway's optional `OLLAMA_GATEWAY_TIMEOUT` defaults to 10 seconds and is bounded to 30 seconds.

## Verify the connection

First test that an unauthenticated request to the tunnel is rejected. Then send an authenticated native Ollama chat request through it using a small unrelated question. Do not place the token in a URL, a committed script, a screenshot, or browser code.

During an application rehearsal, temporarily configure a deliberately lower local Groq request budget to exercise the backup route. Restore the real budget afterward. The transcript should identify `ollama_backup`, and admin health should report an accepted backup reply. Configuration alone does not verify the connection. Test a disconnected gateway too; the student should receive an error and retain the draft, with no new accepted prompt or clue.

The [Ollama chat API](https://docs.ollama.com/api/chat) defines the upstream request and response format. The local Ollama API has no built-in authentication by default, as described in its [authentication documentation](https://docs.ollama.com/api/authentication). Keep it behind this gateway and the authenticated tunnel.
