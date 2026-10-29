import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import logger_db
import provider_budget as budget


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = str(Path(self.folder.name) / "budget.sqlite3")
        settings = {"DATABASE_URL": "", "DATABASE_PATH": self.database,
                    "GROQ_RPM_LIMIT": "30", "GROQ_TPM_LIMIT": "8000",
                    "GROQ_RPD_LIMIT": "1000", "GROQ_TPD_LIMIT": "200000",
                    "GROQ_MAX_CONCURRENT": "100", "GROQ_TEAM_MIN_INTERVAL": "0"}
        for patcher in (patch.dict(os.environ, settings), patch.object(logger_db, "DB_PATH", Path(self.database)), patch.object(logger_db, "DATABASE_URL", "")):
            patcher.start()
            self.addCleanup(patcher.stop)
        logger_db.init_db()

    def test_token_reservation_reconciliation_and_window_expiry(self):
        with patch.dict(os.environ, {"GROQ_TPM_LIMIT": "200"}), patch.object(budget.time, "time", return_value=10000):
            first = budget.reserve(120, "one")
            self.assertTrue(first["allowed"])
            self.assertEqual(budget.reserve(100, "two")["reason"], "budget_tpm")
            budget.complete(first["reservation_id"], 60)
            self.assertTrue(budget.reserve(100, "two")["allowed"])
            self.assertEqual(budget.snapshot()["used"]["tpm"], 160)
        with patch.object(budget.time, "time", return_value=10061):
            self.assertEqual(budget.snapshot()["used"]["tpm"], 0)
            self.assertEqual(budget.snapshot()["used"]["rpd"], 2)

    def test_shared_concurrency_and_crashed_worker_lease(self):
        with patch.dict(os.environ, {"GROQ_MAX_CONCURRENT": "1"}), patch.object(budget.time, "time", return_value=10000):
            first = budget.reserve(100, "one", lease_seconds=90)
            self.assertTrue(first["allowed"])
            self.assertEqual(budget.reserve(100, "two")["reason"], "concurrency")
        with patch.dict(os.environ, {"GROQ_MAX_CONCURRENT": "1"}), patch.object(budget.time, "time", return_value=10091):
            self.assertTrue(budget.reserve(100, "two")["allowed"])
            self.assertEqual(budget.snapshot()["used"]["rpd"], 2)

    def test_daily_request_and_token_budgets(self):
        with patch.dict(os.environ, {"GROQ_RPD_LIMIT": "1"}), patch.object(budget.time, "time", return_value=10000):
            first = budget.reserve(100, "one")
            budget.complete(first["reservation_id"], 100)
        with patch.dict(os.environ, {"GROQ_RPD_LIMIT": "1"}), patch.object(budget.time, "time", return_value=10061):
            self.assertEqual(budget.reserve(100, "two")["reason"], "budget_rpd")
        with patch.dict(os.environ, {"GROQ_TPD_LIMIT": "150"}), patch.object(budget.time, "time", return_value=10061):
            self.assertEqual(budget.reserve(100, "two")["reason"], "budget_tpd")
        with patch.object(budget.time, "time", return_value=96401):
            self.assertTrue(budget.reserve(100, "two")["allowed"])

    def test_cooldown_survives_a_new_process(self):
        budget.cooldown(180)
        code = "import json; from provider_budget import snapshot; print(json.dumps(snapshot()))"
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=dict(os.environ), capture_output=True, text=True, check=True)
        self.assertGreater(json.loads(result.stdout)["cooldown_seconds"], 175)
        self.assertEqual(budget.reserve(100, "one")["reason"], "org_cooldown")

    def test_parallel_processes_cannot_overbook_requests(self):
        code = "import json; from logger_db import init_db; from provider_budget import reserve; init_db(); print(json.dumps(reserve(100)))"
        env = {**os.environ, "GROQ_RPM_LIMIT": "3"}
        def reserve_one(_):
            result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve_one, range(8)))
        self.assertEqual(sum(result["allowed"] for result in results), 3)
        self.assertEqual(budget.snapshot()["used"]["rpm"], 3)

    def test_waiting_less_served_team_gets_next_turn(self):
        with patch.dict(os.environ, {"GROQ_RPM_LIMIT": "1"}), patch.object(budget.time, "time", return_value=10000):
            first = budget.reserve(100, "fast")
            budget.complete(first["reservation_id"], 50)
            self.assertEqual(budget.reserve(100, "waiting")["reason"], "budget_rpm")
        with patch.dict(os.environ, {"GROQ_RPM_LIMIT": "1"}), patch.object(budget.time, "time", return_value=10061):
            self.assertEqual(budget.reserve(100, "fast")["reason"], "fair_turn")
            self.assertTrue(budget.reserve(100, "waiting")["allowed"])

    def test_abandoned_fairness_ticket_expires(self):
        with patch.dict(os.environ, {"GROQ_RPM_LIMIT": "1"}), patch.object(budget.time, "time", return_value=10000):
            first = budget.reserve(100, "fast")
            budget.complete(first["reservation_id"], 50)
            budget.reserve(100, "abandoned")
        with patch.dict(os.environ, {"GROQ_RPM_LIMIT": "1"}), patch.object(budget.time, "time", return_value=10076):
            self.assertTrue(budget.reserve(100, "fast")["allowed"])

    def test_changing_a_key_does_not_reset_shared_usage(self):
        with patch.dict(os.environ, {"GROQ_RPM_LIMIT": "1", "GROQ_API_KEY": "first-test-key"}):
            first = budget.reserve(100, "one")
            budget.complete(first["reservation_id"], 50)
        with patch.dict(os.environ, {"GROQ_RPM_LIMIT": "1", "GROQ_API_KEY": "different-test-key"}):
            self.assertEqual(budget.reserve(100, "two")["reason"], "budget_rpm")


@unittest.skipUnless(os.getenv("PG_ADMIN_TEST_URL"), "Set PG_ADMIN_TEST_URL for an isolated local PostgreSQL budget test.")
class PostgresBudgetTests(unittest.TestCase):
    def test_shared_budget_concurrency_cooldown_and_restart(self):
        import psycopg
        import secrets
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        admin = os.environ["PG_ADMIN_TEST_URL"]
        self.assertIn(conninfo_to_dict(admin).get("host"), ("localhost", "127.0.0.1", "::1"))
        database = "aarohan_budget_" + secrets.token_hex(8)
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        env = {**os.environ, "DATABASE_URL": make_conninfo(admin, dbname=database),
               "GROQ_RPM_LIMIT": "3", "GROQ_TPM_LIMIT": "8000", "GROQ_RPD_LIMIT": "1000",
               "GROQ_TPD_LIMIT": "200000", "GROQ_MAX_CONCURRENT": "100", "GROQ_TEAM_MIN_INTERVAL": "0"}
        def execute(code):
            result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        try:
            code = "import json; from logger_db import init_db; from provider_budget import reserve; init_db(); print(json.dumps(reserve(100)))"
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                admissions = list(pool.map(lambda _: execute(code), range(8)))
            self.assertEqual(sum(item["allowed"] for item in admissions), 3)
            state = execute("import json; from provider_budget import snapshot; print(json.dumps(snapshot()))")
            self.assertEqual(state["used"]["rpm"], 3)
            execute("import json; from provider_budget import cooldown; cooldown(180); print(json.dumps(True))")
            state = execute("import json; from provider_budget import snapshot; print(json.dumps(snapshot()))")
            self.assertGreater(state["cooldown_seconds"], 170)
        finally:
            with psycopg.connect(admin, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


if __name__ == "__main__":
    unittest.main()
