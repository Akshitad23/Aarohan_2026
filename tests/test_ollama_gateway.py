import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import ollama_gateway as gateway


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.token = "test-token-" * 4
        self.app = gateway.create_gateway(self.token, "installed-test-model")
        self.headers = {"Authorization": "Bearer " + self.token}
        self.payload = {"model": "installed-test-model", "messages": [{"role": "system", "content": "Tutor rules"}, {"role": "user", "content": "Explain an unrelated example."}], "stream": False, "options": {"num_predict": 256, "num_ctx": 4096, "temperature": 0.5}}

    def response(self, content="Compare letter positions in an unrelated example."):
        return io.BytesIO(json.dumps({"done": True, "message": {"content": content, "thinking": "Private reasoning omitted"}, "internal": "Not forwarded"}).encode())

    def test_authentication_precedes_upstream_access(self):
        with patch.object(gateway, "_open_upstream") as upstream:
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                result = self.app.test_client().post("/api/chat", json=self.payload, headers=headers)
                self.assertEqual(result.status_code, 401)
            upstream.assert_not_called()

    def test_only_fixed_localhost_model_and_short_reply_are_forwarded(self):
        captured = {}
        def upstream(request, timeout):
            captured["request"] = request
            return self.response()
        with patch.object(gateway, "_open_upstream", side_effect=upstream):
            result = self.app.test_client().post("/api/chat", json=self.payload, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(captured["request"].full_url, "http://127.0.0.1:11434/api/chat")
        self.assertIsNone(captured["request"].get_header("Authorization"))
        self.assertEqual(json.loads(captured["request"].data)["model"], "installed-test-model")
        self.assertNotIn("thinking", result.get_json()["message"])
        self.assertNotIn("internal", result.get_json())

    def test_arbitrary_models_urls_and_options_are_rejected(self):
        for change in ({"model": "other-model"}, {"url": "https://elsewhere.example"}, {"stream": True}, {"options": {"num_predict": 9999}}, {"options": {"num_ctx": 99999}}, {"options": {"tools": []}}):
            with patch.object(gateway, "_open_upstream") as upstream:
                result = self.app.test_client().post("/api/chat", json={**self.payload, **change}, headers=self.headers)
                self.assertEqual(result.status_code, 400)
                upstream.assert_not_called()

    def test_context_and_payload_size_are_bounded(self):
        payload = {**self.payload, "messages": [{"role": "system", "content": "x" * 2800}, {"role": "user", "content": "too large"}]}
        with patch.object(gateway, "_open_upstream") as upstream:
            self.assertEqual(self.app.test_client().post("/api/chat", json=payload, headers=self.headers).status_code, 400)
            self.assertEqual(self.app.test_client().post("/api/chat", data="x" * 20000, content_type="application/json", headers=self.headers).status_code, 413)
            upstream.assert_not_called()

    def test_concurrency_one_returns_retry_instead_of_queueing(self):
        entered, release = threading.Event(), threading.Event()
        results = []
        def upstream(request, timeout):
            entered.set()
            release.wait(3)
            return self.response()
        def first_request():
            results.append(self.app.test_client().post("/api/chat", json=self.payload, headers=self.headers).status_code)
        with patch.object(gateway, "_open_upstream", side_effect=upstream):
            worker = threading.Thread(target=first_request)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                second = self.app.test_client().post("/api/chat", json=self.payload, headers=self.headers)
                self.assertEqual(second.status_code, 429)
                self.assertEqual(second.headers["Retry-After"], "5")
            finally:
                release.set()
                worker.join(3)
        self.assertEqual(results, [200])

    def test_upstream_errors_do_not_leak_and_release_capacity(self):
        with patch.object(gateway, "_open_upstream", side_effect=[RuntimeError("sensitive details"), self.response()]):
            first = self.app.test_client().post("/api/chat", json=self.payload, headers=self.headers)
            second = self.app.test_client().post("/api/chat", json=self.payload, headers=self.headers)
        self.assertEqual(first.status_code, 502)
        self.assertNotIn("sensitive", first.get_data(as_text=True))
        self.assertEqual(second.status_code, 200)

    def test_invalid_large_or_partial_model_output_is_rejected(self):
        bodies = [self.response("x" * 1201), io.BytesIO(json.dumps({"done": False, "message": {"content": "partial"}}).encode()), io.BytesIO(b"x" * 65537)]
        with patch.object(gateway, "_open_upstream", side_effect=bodies):
            for _ in bodies:
                self.assertEqual(self.app.test_client().post("/api/chat", json=self.payload, headers=self.headers).status_code, 502)

    def test_missing_or_weak_gateway_configuration_fails_startup(self):
        for token, model in (("short", "installed"), (self.token, "")):
            with self.assertRaises(RuntimeError):
                gateway.create_gateway(token, model)


if __name__ == "__main__":
    unittest.main()
