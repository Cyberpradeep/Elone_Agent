"""
Regression suite verifying P0-2 (C1): all ungoverned SOP ingestion bypass paths
(POST /api/uploads/scan, scheduler.py, MCP ingest_sop / scan_uploads_now,
execution_planner.convert_raw_sop_to_okf, and CLI run.py) are blocked and cannot
write playbooks to knowledge_base/sops/.
"""

import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import scheduler  # noqa: E402
import mcp_server  # noqa: E402
from agents.a2_structuring import execution_planner  # noqa: E402
from server import app  # noqa: E402


class TestGovernanceBypassDisabled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"

    def setUp(self):
        self.client = TestClient(app)

    def test_01_convert_raw_sop_to_okf_is_blocked(self):
        """convert_raw_sop_to_okf refuses direct disk commits without A3-A6 governance."""
        with self.assertRaises(ValueError) as ctx:
            execution_planner.convert_raw_sop_to_okf("nonexistent_bypass.txt")
        self.assertIn("blocked", str(ctx.exception).lower())
        self.assertIn("c1", str(ctx.exception).lower())

    def test_02_scheduler_cycle_and_daemon_are_disabled(self):
        """run_ingestion_cycle fails closed and start_sop_ingestion_scheduler spawns no thread."""
        with patch("threading.Thread") as mock_thread:
            status = scheduler.start_sop_ingestion_scheduler(interval_minutes=1)
        mock_thread.assert_not_called()
        self.assertFalse(status["running"])
        self.assertTrue(status.get("disabled"))

        reported = scheduler.get_scheduler_status()
        self.assertFalse(reported["running"])
        self.assertTrue(reported.get("disabled"))

        with self.assertRaises(RuntimeError) as ctx:
            scheduler.run_ingestion_cycle()
        self.assertIn("disabled", str(ctx.exception).lower())

    def test_03_http_scan_endpoint_returns_410_and_never_runs_cycle(self):
        """POST /api/uploads/scan returns HTTP 410 with UNGOVERNED_SCAN_DISABLED."""
        with patch("agents.a2_structuring.okf_builder.write_okf_playbook") as mock_write:
            resp = self.client.post("/api/uploads/scan")
        self.assertEqual(resp.status_code, 410)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "UNGOVERNED_SCAN_DISABLED")
        self.assertEqual(data["use_endpoint"], "/api/uploads/ingest")
        mock_write.assert_not_called()

    def test_04_mcp_write_tools_are_blocked_and_plan_sop_is_read_only(self):
        """MCP ingest_sop and scan_uploads_now return GOVERNANCE BLOCKED and write nothing."""
        with patch("agents.a2_structuring.okf_builder.write_okf_playbook") as mock_write:
            ingest_out = mcp_server.ingest_sop("any_sample.txt")
            scan_out = mcp_server.scan_uploads_now()
        mock_write.assert_not_called()
        self.assertIn("GOVERNANCE BLOCKED", ingest_out)
        scan_payload = json.loads(scan_out)
        self.assertFalse(scan_payload["success"])
        self.assertEqual(scan_payload["error_code"], "UNGOVERNED_SCAN_DISABLED")
        self.assertIn("GOVERNANCE BLOCKED", scan_payload["message"])

    def test_05_mcp_cli_harness_does_not_start_scheduler_and_passes(self):
        """mcp_server.py --test verifies blocked write tools cleanly without starting scheduler."""
        env = {**os.environ, "ELONE_ALLOW_INSECURE_DEV_KEY": "1"}
        proc = subprocess.run(
            [sys.executable, os.path.join(BACKEND_DIR, "mcp_server.py"), "--test"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}")
        self.assertIn("GOVERNANCE BLOCKED", proc.stdout or "")
        self.assertNotIn("Starting background worker", proc.stderr or "")

    def test_06_legacy_cli_run_py_flags_are_blocked(self):
        """run.py --scan / --watch / --file refuse ungoverned writes with exit code 1."""
        env = {**os.environ, "ELONE_ALLOW_INSECURE_DEV_KEY": "1"}
        for args in (["--scan"], ["--watch"], ["--file", "dummy.txt"]):
            proc = subprocess.run(
                [sys.executable, os.path.join(BACKEND_DIR, "run.py"), *args],
                cwd=BACKEND_DIR,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertNotEqual(proc.returncode, 0, msg=f"Expected failure for {args}, stdout={proc.stdout}")
            self.assertIn("GOVERNANCE BLOCKED", proc.stdout or "")

    def test_07_telemetry_scheduler_endpoints_report_disabled(self):
        """GET /api/scheduler and GET /api/overview report disabled=True and running=False."""
        r_sched = self.client.get("/api/scheduler")
        self.assertEqual(r_sched.status_code, 200)
        sched = r_sched.json()
        self.assertTrue(sched.get("disabled"))
        self.assertFalse(sched.get("running"))

        r_over = self.client.get("/api/overview")
        self.assertEqual(r_over.status_code, 200)
        over_sched = r_over.json().get("scheduler", {})
        self.assertTrue(over_sched.get("disabled"))
        self.assertFalse(over_sched.get("running"))


if __name__ == "__main__":
    unittest.main()
