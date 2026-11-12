"""
Regression tests for live ingestion progress reporting across RBAC roles and multi-image labels.
Verifies:
- `gemini_monitor.monitor` binds non-billing per-job `progress_calls` safely and bounds memory.
- `GET /api/governance/jobs` and `GET /api/governance/jobs/{job_id}` expose `progress_calls`
  to tenant-authorized human roles (`process_owner`, `security_reviewer`, `admin`) while
  keeping `GET /api/telemetry` admin-only and blocking cross-tenant/agent access.
- `api.routes_ingestion._run_cancellable` binds `ctl.job_id` onto the worker threadpool thread
  and cleans up afterward.
"""

import asyncio
import datetime
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from auth.models import (  # noqa: E402
    AuthPrincipal,
    ROLE_ADMIN,
    ROLE_AGENT,
    ROLE_PROCESS_OWNER,
)
from auth.tokens import create_access_token  # noqa: E402
from gemini_monitor import monitor  # noqa: E402
from schemas.governance_models import JobRecord  # noqa: E402


def _make_token(identity: str, roles, tenant_id: str, clearance: str = "L3", actor_type: str = "human") -> str:
    principal = AuthPrincipal(
        sub=identity,
        identity=identity,
        display_name=identity,
        roles=tuple(roles),
        tenant_id=tenant_id,
        clearance=clearance,
        actor_type=actor_type,
        agent_id="svc-1" if actor_type == "agent" else None,
        agent_persona="L1_TRIAGE" if actor_type == "agent" else None,
    )
    tok, _, _ = create_access_token(principal)
    return tok


class TestJobProgressMonitor(unittest.TestCase):
    def test_bind_record_clear_and_no_billing_fields(self):
        job_id = "job_unit_progress_1"
        monitor.clear_job_progress(job_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            usage_path = os.path.join(tmpdir, "daily_usage.json")
            with patch.object(monitor, "USAGE_FILE", usage_path):
                prev = monitor.bind_job_progress(job_id)
                try:
                    monitor.record_call(
                        caller="vlm_image_analysis",
                        model="meta/llama-3.2-90b-vision-instruct",
                        provider="nvidia",
                        input_tokens=1036,
                        output_tokens=382,
                        image_tokens=560,
                        sop_id="SOP-TEST1",
                    )
                    monitor.record_call(
                        caller="test_runner",
                        model="noop",
                        provider="nvidia",
                        input_tokens=1,
                        output_tokens=1,
                    )
                finally:
                    monitor.reset_job_progress(prev)

        calls = monitor.get_job_progress(job_id)
        self.assertEqual(len(calls), 1)
        ev = calls[0]
        self.assertEqual(ev["caller"], "vlm_image_analysis")
        self.assertEqual(ev["model"], "meta/llama-3.2-90b-vision-instruct")
        self.assertEqual(ev["input_tokens"], 1036)
        self.assertEqual(ev["output_tokens"], 382)
        self.assertEqual(ev["image_tokens"], 560)
        self.assertTrue(ev["timestamp"])
        for forbidden in ("cost_usd", "cost_inr", "provider", "calls_remaining", "max_daily_calls"):
            self.assertNotIn(forbidden, ev)

        monitor.clear_job_progress(job_id)
        self.assertEqual(monitor.get_job_progress(job_id), [])

    def test_job_progress_map_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            usage_path = os.path.join(tmpdir, "daily_usage.json")
            saved_map = dict(monitor._JOB_PROGRESS)
            try:
                monitor._JOB_PROGRESS.clear()
                with patch.object(monitor, "USAGE_FILE", usage_path), patch.object(
                    monitor, "_MAX_JOB_PROGRESS_ENTRIES", 3
                ):
                    for i in range(5):
                        prev = monitor.bind_job_progress(f"job_cap_{i}")
                        try:
                            monitor.record_call(
                                caller="triage_router",
                                model="gemini-2.5-flash",
                                provider="google",
                                input_tokens=10,
                                output_tokens=5,
                            )
                        finally:
                            monitor.reset_job_progress(prev)
                self.assertEqual(len(monitor._JOB_PROGRESS), 3)
                self.assertEqual(monitor.get_job_progress("job_cap_0"), [])
                self.assertEqual(len(monitor.get_job_progress("job_cap_4")), 1)
            finally:
                monitor._JOB_PROGRESS.clear()
                monitor._JOB_PROGRESS.update(saved_map)

    def test_run_cancellable_binds_job_progress_on_worker_thread(self):
        from api.routes_ingestion import _IngestControl, _run_cancellable

        job_id = "job_worker_bind_1"
        monitor.clear_job_progress(job_id)
        ctl = _IngestControl("owner@tenant_a")
        ctl.job_id = job_id

        with tempfile.TemporaryDirectory() as tmpdir:
            usage_path = os.path.join(tmpdir, "daily_usage.json")
            with patch.object(monitor, "USAGE_FILE", usage_path):
                def _worker():
                    monitor.record_call(
                        caller="execution_planning",
                        model="gemini-2.5-flash",
                        provider="google",
                        input_tokens=400,
                        output_tokens=150,
                    )
                    return "ok"

                res = asyncio.run(_run_cancellable(ctl, _worker))

        self.assertEqual(res, "ok")
        calls = monitor.get_job_progress(job_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["caller"], "execution_planning")
        monitor.clear_job_progress(job_id)


class TestGovernanceJobsProgressRBAC(unittest.TestCase):
    def setUp(self):
        from server import app
        from api import context as api_ctx

        self.client = TestClient(app)
        self.ledger = api_ctx.governance_ledger
        self.job_id = "job_rbac_live_progress"
        self.idle_job_id = "job_rbac_idle_progress"

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._orig_jobs = dict(self.ledger._jobs)
        self.ledger._jobs[self.job_id] = JobRecord(
            job_id=self.job_id,
            sop_id="SOP-PROGRESS1",
            tenant_id="tenant_alpha",
            version=1,
            content_sha256="a" * 64,
            uploaded_by="owner_a@example.com",
            current_state="structuring",
            created_at=now,
            updated_at=now,
        )
        self.ledger._jobs[self.idle_job_id] = JobRecord(
            job_id=self.idle_job_id,
            sop_id="SOP-PROGRESS2",
            tenant_id="tenant_alpha",
            version=1,
            content_sha256="b" * 64,
            uploaded_by="owner_a@example.com",
            current_state="received",
            created_at=now,
            updated_at=now,
        )
        monitor.clear_job_progress(self.job_id)
        monitor.clear_job_progress(self.idle_job_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            usage_path = os.path.join(tmpdir, "daily_usage.json")
            with patch.object(monitor, "USAGE_FILE", usage_path):
                prev = monitor.bind_job_progress(self.job_id)
                try:
                    monitor.record_call("vlm_image_analysis", "vlm-1", "nvidia", 900, 300, 560)
                    monitor.record_call("vlm_image_analysis", "vlm-1", "nvidia", 1036, 382, 560)
                    monitor.record_call("triage_router", "gemini-2.5-flash", "google", 500, 120)
                finally:
                    monitor.reset_job_progress(prev)

    def tearDown(self):
        self.ledger._jobs.clear()
        self.ledger._jobs.update(self._orig_jobs)
        monitor.clear_job_progress(self.job_id)
        monitor.clear_job_progress(self.idle_job_id)

    def test_process_owner_sees_own_tenant_progress_calls_and_not_telemetry(self):
        tok_owner_a = _make_token("owner_a@example.com", [ROLE_PROCESS_OWNER], "tenant_alpha")
        hdrs = {"Authorization": f"Bearer {tok_owner_a}"}

        with patch.object(self.ledger, "load", lambda: None):
            r_list = self.client.get("/api/governance/jobs", headers=hdrs)
            self.assertEqual(r_list.status_code, 200)
            jobs_by_id = {j["job_id"]: j for j in r_list.json()["jobs"]}

            self.assertIn(self.job_id, jobs_by_id)
            p_calls = jobs_by_id[self.job_id].get("progress_calls")
            self.assertIsInstance(p_calls, list)
            self.assertEqual([c["caller"] for c in p_calls], ["vlm_image_analysis", "vlm_image_analysis", "triage_router"])
            for ev in p_calls:
                self.assertNotIn("cost_usd", ev)
                self.assertNotIn("cost_inr", ev)

            self.assertNotIn("progress_calls", jobs_by_id[self.idle_job_id])

            r_detail = self.client.get(f"/api/governance/jobs/{self.job_id}", headers=hdrs)
            self.assertEqual(r_detail.status_code, 200)
            self.assertEqual(len(r_detail.json()["progress_calls"]), 3)

        r_tel = self.client.get("/api/telemetry", headers=hdrs)
        self.assertEqual(r_tel.status_code, 403)

    def test_cross_tenant_and_agent_cannot_see_job_progress(self):
        tok_owner_b = _make_token("owner_b@example.com", [ROLE_PROCESS_OWNER], "tenant_beta")
        with patch.object(self.ledger, "load", lambda: None):
            r_list_b = self.client.get("/api/governance/jobs", headers={"Authorization": f"Bearer {tok_owner_b}"})
            self.assertEqual(r_list_b.status_code, 200)
            self.assertNotIn(self.job_id, [j["job_id"] for j in r_list_b.json()["jobs"]])

            r_det_b = self.client.get(
                f"/api/governance/jobs/{self.job_id}",
                headers={"Authorization": f"Bearer {tok_owner_b}"},
            )
            self.assertEqual(r_det_b.status_code, 403)

        tok_agent_a = _make_token("agent@tenant_alpha", [ROLE_AGENT], "tenant_alpha", actor_type="agent")
        r_agent = self.client.get("/api/governance/jobs", headers={"Authorization": f"Bearer {tok_agent_a}"})
        self.assertEqual(r_agent.status_code, 403)

        tok_admin = _make_token("admin@example.com", [ROLE_ADMIN], "tenant_alpha")
        with patch.object(self.ledger, "load", lambda: None):
            r_det_admin = self.client.get(
                f"/api/governance/jobs/{self.job_id}",
                headers={"Authorization": f"Bearer {tok_admin}"},
            )
            self.assertEqual(r_det_admin.status_code, 200)
            self.assertEqual(len(r_det_admin.json()["progress_calls"]), 3)


if __name__ == "__main__":
    unittest.main()

