"""Run separately on the organizer's Windows computer behind an HTTPS tunnel."""

import json
import os
from pathlib import Path
import secrets
import threading
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import Flask, jsonify, request

UPSTREAM = "http://127.0.0.1:11434/api/chat"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Upstream redirects are disabled", headers, fp)


_open_upstream = build_opener(NoRedirect).open


def create_gateway(token=None, model=None):
    token = token if token is not None else os.getenv("OLLAMA_BACKUP_TOKEN", "").strip()
    model = model if model is not None else os.getenv("OLLAMA_BACKUP_MODEL", "").strip()
    if len(token) < 32 or not token.isascii() or not model or len(model) > 128 or any(character.isspace() for character in model):
        raise RuntimeError("Set OLLAMA_BACKUP_TOKEN to at least 32 characters and OLLAMA_BACKUP_MODEL to one installed model.")
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16384
    capacity = threading.BoundedSemaphore(1)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/api/chat")
    def chat():
        authorization = request.headers.get("Authorization", "")
        if not authorization.isascii() or not secrets.compare_digest(authorization, "Bearer " + token):
            return jsonify(error="Authentication required."), 401
        data = request.get_json(silent=True)
        if (not isinstance(data, dict) or set(data) - {"model", "messages", "stream", "options"}
                or data.get("model") != model or data.get("stream") is not False):
            return jsonify(error="Use the configured model and a non-streaming chat request."), 400
        messages = data.get("messages")
        if not isinstance(messages, list) or not 2 <= len(messages) <= 6:
            return jsonify(error="Send two to six text messages."), 400
        for index, message in enumerate(messages):
            expected_role = "system" if index == 0 else "user" if index % 2 else "assistant"
            if (not isinstance(message, dict) or set(message) != {"role", "content"}
                    or message["role"] != expected_role or not isinstance(message["content"], str)):
                return jsonify(error="Use a system message, optional user/assistant pairs, and a final user message."), 400
        if messages[-1]["role"] != "user" or sum(len(message["content"].encode("utf-8")) for message in messages) > 2800:
            return jsonify(error="The text context is too large or lacks a final user message."), 400
        options = data.get("options", {})
        if not isinstance(options, dict) or set(options) - {"temperature", "num_predict", "num_ctx"}:
            return jsonify(error="Unsupported generation options."), 400
        for name, lower, upper, default in (("num_predict", 1, 256, 256), ("num_ctx", 4096, 4096, 4096), ("temperature", 0, 1, 0.5)):
            value = options.get(name, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not lower <= value <= upper or name != "temperature" and not isinstance(value, int):
                return jsonify(error="Generation options exceed the gateway limits."), 400
        if not capacity.acquire(blocking=False):
            return jsonify(error="The backup model is busy. Retry later."), 429, {"Retry-After": "5"}
        try:
            payload = {"model": model, "messages": messages, "stream": False,
                       "options": {"temperature": options.get("temperature", 0.5),
                                   "num_predict": options.get("num_predict", 256),
                                   "num_ctx": options.get("num_ctx", 4096)}}
            upstream = Request(UPSTREAM, data=json.dumps(payload).encode("utf-8"),
                               headers={"Content-Type": "application/json"}, method="POST")
            timeout = max(1, min(30, float(os.getenv("OLLAMA_GATEWAY_TIMEOUT", "10"))))
            with _open_upstream(upstream, timeout=timeout) as response:
                body = response.read(65537)
            if len(body) > 65536:
                return jsonify(error="The backup model returned an oversized response."), 502
            output = json.loads(body)
            content = output.get("message", {}).get("content")
            if output.get("error") or output.get("done") is not True or not isinstance(content, str) or not content.strip() or len(content) > 1200:
                return jsonify(error="The backup model did not return a valid short response."), 502
            return jsonify(model=model, done=True, message={"role": "assistant", "content": content})
        except TimeoutError:
            return jsonify(error="The backup model did not respond in time."), 504
        except Exception as error:
            print(f"[Ollama gateway] {type(error).__name__}")
            return jsonify(error="The backup model is unavailable."), 502
        finally:
            capacity.release()

    return app


if __name__ == "__main__":
    from dotenv import load_dotenv
    from waitress import serve
    load_dotenv(Path(__file__).parent / ".env")
    gateway_app = create_gateway()
    print("Starting Ollama gateway on http://127.0.0.1:11435. A separate authenticated HTTPS tunnel is required for Render.")
    serve(gateway_app, host="127.0.0.1", port=11435, threads=4)
