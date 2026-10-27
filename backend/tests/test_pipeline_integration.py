"""
Integration Tests for Governance Pipeline, Dual Export & Server APIs (Step 4)
=============================================================================
Tests end-to-end integration across:
1. Dual-export generation (Canonical JSON 1.0 + OKF Playbook .md).
2. Step auto-synchronization from Canonical JSON into OKF YAML frontmatter with HMAC re-signing.
3. Starlette REST API endpoints for Governance Lifecycle, Review Tasks, and Downstream Search.
"""

import os
import sys
import json
import uuid
import tempfile
import unittest
from starlette.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from server import app, governance_ledger, retrieval_index
from agents.a2_structuring.canonical_builder import (
    build_canonical_sop_from_draft,
    write_canonical_sop_json,
    sync_canonical_to_playbook,
)
from utils.security import verify_playbook_before_execution
from schemas.canonical_sop_schema import validate_canonical_sop_dict


class TestPipelineIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"

    def setUp(self):
        self.client = TestClient(app)

    def test_01_build_canonical_sop_from_draft(self):
        """Dual export builder generates valid Canonical SOP JSON 1.0 from OKF draft."""
        mock_draft = {
            "frontmatter": {
                "sop_id": "SOP-TEST-INT-01",
                "title": "Endpoint Cache Clean Procedure",
                "category": "software",
                "description": "Purges DNS and browser caches on Windows workstations.",
                "steps": [
                    {
                        "step_number": 1,
                        "sop_step_description": "Flush Windows DNS resolver cache",
                        "step_type": "command",
                        "command": "ipconfig /flushdns",
                        "shell": "powershell",
                    },
                    {
                        "step_number": 2,
                        "sop_step_description": "Clear Chrome temporary socket pools",
                        "step_type": "command",
                        "command": "Get-Process chrome | Stop-Process -Force",
                        "shell": "powershell",
                    },
                ],
            }
        }
        canonical_dict = build_canonical_sop_from_draft(mock_draft, raw_text="Flush Windows DNS resolver cache\nClear Chrome temporary socket pools")
        self.assertEqual(canonical_dict["sop_id"], "SOP-TEST-INT-01")
        self.assertEqual(len(canonical_dict["steps"]), 2)
        self.assertEqual(canonical_dict["steps"][0]["action"], "Flush Windows DNS resolver cache")
        self.assertEqual(canonical_dict["steps"][0]["n"], 1)

        # Validate against Canonical Schema 1.0
        valid, errors, model = validate_canonical_sop_dict(canonical_dict)
        self.assertTrue(valid, f"Canonical JSON validation failed: {errors}")
        self.assertIsNotNone(model)

    def test_02_sync_canonical_to_playbook_and_hmac_resigning(self):
        """Editing step in Canonical JSON synchronizes into .md YAML frontmatter with valid HMAC."""
        mock_canonical = {
            "sop_id": "SOP-SYNC-01",
            "title": "Service Restart Workflow",
            "department": {"value": "Infrastructure"},
            "purpose": {"text": "Restarts stuck background services."},
            "steps": [
                {
                    "n": 1,
                    "action": "Updated action: Gracefully stop the application service",
                    "input": "Stop-Service -Name AppService",
                    "expected_outcome": "Service stopped successfully",
                },
                {
                    "n": 2,
                    "action": "Updated action: Start the application service and verify status",
                    "input": "Start-Service -Name AppService",
                    "expected_outcome": "Service running",
                },
            ],
        }

        # Sync to playbook
        md_path = sync_canonical_to_playbook(mock_canonical, category="infrastructure")
        self.assertTrue(os.path.exists(md_path))

        try:
            # Read the synced .md file
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("Updated action: Gracefully stop the application service", content)
            self.assertIn("integrity_hmac_sha256", content)

            # Cryptographic verification: verify HMAC is valid!
            is_valid, err, _ = verify_playbook_before_execution(md_path)
            self.assertTrue(is_valid, f"HMAC signature verification failed: {err}")
        finally:
            if os.path.exists(md_path):
                os.remove(md_path)

    def test_03_api_governance_jobs_and_review_tasks(self):
        """REST APIs return jobs list and review tasks with live overdue status."""
        uid = uuid.uuid4().hex[:6]
        job_id = f"job_api_{uid}"
        sop_id = f"SOP-API-{uid}"
        job = governance_ledger.start_job(
            job_id=job_id,
            sop_id=sop_id,
            tenant_id="tn_northwind",
            content_sha256=f"hash_{uid}",
            uploaded_by="uploader@example.com",
        )
        governance_ledger.transition_state(job_id, "extracting")
        governance_ledger.transition_state(job_id, "scanning")
        governance_ledger.transition_state(job_id, "structuring")
        governance_ledger.transition_state(job_id, "assessing")
        task = governance_ledger.create_review_task(job_id, 35, "L1")

        # 1. GET /api/governance/jobs
        resp = self.client.get("/api/governance/jobs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("jobs", data)
        self.assertTrue(any(j["job_id"] == job_id for j in data["jobs"]))

        # 2. GET /api/governance/review-tasks
        resp = self.client.get("/api/governance/review-tasks")
        self.assertEqual(resp.status_code, 200)
        tasks_data = resp.json()
        self.assertIn("tasks", tasks_data)
        matching_task = next((t for t in tasks_data["tasks"] if t["task_id"] == task.task_id), None)
        self.assertIsNotNone(matching_task)
        self.assertIn("is_overdue", matching_task)

    def test_04_api_record_decision_separation_of_duties_enforced(self):
        """Self-approval is rejected by API with 403 and error_code 'separation_of_duties'."""
        uid = uuid.uuid4().hex[:6]
        job_id = f"job_sod_{uid}"
        sop_id = f"SOP-SOD-{uid}"
        job = governance_ledger.start_job(
            job_id=job_id,
            sop_id=sop_id,
            tenant_id="tn_northwind",
            content_sha256=f"hash_sod_{uid}",
            uploaded_by="alice@example.com",
        )
        governance_ledger.transition_state(job_id, "extracting")
        governance_ledger.transition_state(job_id, "scanning")
        governance_ledger.transition_state(job_id, "structuring")
        governance_ledger.transition_state(job_id, "assessing")
        task = governance_ledger.create_review_task(job_id, 20, "L0")

        # Alice attempts to approve her own document -> 403 Forbidden!
        resp = self.client.post(
            f"/api/governance/review-tasks/{task.task_id}/decision",
            json={
                "decision": "approve",
                "reviewer": "alice@example.com",
                "actor_type": "human",
            },
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error_code"), "separation_of_duties")

        # Bob (independent human) approves -> 200 Success!
        resp = self.client.post(
            f"/api/governance/review-tasks/{task.task_id}/decision",
            json={
                "decision": "approve",
                "reviewer": "bob@example.com",
                "actor_type": "human",
                "traceability_pct": 95.0,
                "completeness_pct": 90.0,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("job_state"), "approved")

    def test_05_api_publish_and_downstream_search(self):
        """Approved SOP publishes via API and becomes searchable with clearance filtering."""
        uid = uuid.uuid4().hex[:6]
        job_id = f"job_pub_{uid}"
        sop_id = f"SOP-PUB-{uid}"
        content_hash = f"hash_pub_{uid}"
        job = governance_ledger.start_job(
            job_id=job_id,
            sop_id=sop_id,
            tenant_id="tn_northwind",
            content_sha256=content_hash,
            uploaded_by="alice@example.com",
        )
        governance_ledger.transition_state(job_id, "extracting")
        governance_ledger.transition_state(job_id, "scanning")
        governance_ledger.transition_state(job_id, "structuring")
        governance_ledger.transition_state(job_id, "assessing")
        task = governance_ledger.create_review_task(job_id, 55, "L2")  # L2 Confidential

        # Approve
        self.client.post(
            f"/api/governance/review-tasks/{task.task_id}/decision",
            json={
                "decision": "approve",
                "reviewer": "charlie@example.com",
                "actor_type": "human",
            },
        )

        # Publish via POST /api/governance/sops/{sop_id}/publish
        canonical_sop = {
            "schema_version": "1.0",
            "sop_id": sop_id,
            "version": 1,
            "tenant_id": "tn_northwind",
            "title": f"Secure Secret Storage Configuration {uid}",
            "department": {"value": "Security"},
            "classification": {"level": "L2", "score": 55},
            "lifecycle": {"state": "published"},
            "purpose": {"text": f"Configures enterprise vault tokens {uid}."},
            "source": {"sha256": content_hash},
            "steps": [],
        }
        resp = self.client.post(
            f"/api/governance/sops/{sop_id}/publish",
            json={"canonical_sop": canonical_sop},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "published")
        self.assertTrue(data.get("citation").startswith(f"{sop_id}@v1#"))

        # Test Downstream Search: L1 agent cannot see L2 SOP
        resp_l1 = self.client.post(
            "/api/governance/downstream/search",
            json={
                "query": f"vault tokens {uid}",
                "tenant_id": "tn_northwind",
                "clearance_level": "L1",
            },
        )
        self.assertEqual(resp_l1.status_code, 200)
        returned_l1_ids = {r["sop_id"] for r in resp_l1.json()["results"]}
        self.assertNotIn(sop_id, returned_l1_ids)

        # Test Downstream Search: L2 agent CAN see L2 SOP
        resp_l2 = self.client.post(
            "/api/governance/downstream/search",
            json={
                "query": f"vault tokens {uid}",
                "tenant_id": "tn_northwind",
                "clearance_level": "L2",
            },
        )
        self.assertEqual(resp_l2.status_code, 200)
        returned_l2_ids = {r["sop_id"] for r in resp_l2.json()["results"]}
        self.assertIn(sop_id, returned_l2_ids)

    def test_06_human_in_the_loop_before_saving(self):
        """Ingestion creates review task and halts at awaiting_review without saving to sops/."""
        import glob
        from unittest.mock import patch
        uid = uuid.uuid4().hex[:6]
        sop_id = f"SOP-TEST-{uid}"
        filename = f"test_sop_{uid}.txt"
        uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "_uploads"))
        filepath = os.path.join(uploads_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Title: Flush System Diagnostics {uid}\nStep 1: Test connectivity\nStep 2: Flush caches and restart")

        mock_draft = {
            "frontmatter": {
                "type": "Playbook",
                "sop_id": sop_id,
                "title": "Flush System Diagnostics",
                "platform": "system",
                "category": "system",
                "target_os": "windows",
                "description": "Diagnostic and cache flush playbook.",
                "confidence_score": 0.95,
                "confidence_level": "High",
                "confidence_reason": "Deterministic test mock",
                "required_entities": ["email"],
                "trigger_words": ["flush", "diagnostics"],
                "steps": [
                    {
                        "step_number": 1,
                        "description": "Test connectivity",
                        "action": "run_command",
                        "step_type": "command",
                        "command": "ping 127.0.0.1",
                        "source_text_quote": "Step 1: Test connectivity",
                    },
                    {
                        "step_number": 2,
                        "description": "Flush caches and restart",
                        "action": "run_command",
                        "step_type": "command",
                        "command": "ipconfig /flushdns",
                        "source_text_quote": "Step 2: Flush caches and restart",
                    },
                ],
            },
            "is_executable": True,
            "parser_type": "text",
            "raw_chars": 90,
            "reasoning_chain": ["Step 1 extracted", "Step 2 extracted"],
            "confidence_score": 0.95,
            "confidence_level": "High",
            "is_valid": True,
            "validation_errors": [],
        }

        try:
            with patch("api.routes_ingestion.jit_converter.plan_okf_from_raw", return_value=mock_draft):
                resp = self.client.post("/api/uploads/ingest", json={"filename": filename, "sop_id": sop_id})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get("status"), "awaiting_review")
            self.assertIn("task_id", data)
            resp_sop_id = data.get("sop_id")
            self.assertEqual(resp_sop_id, sop_id)

            # Check that the playbook was NOT saved to sops/ yet!
            sops_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "sops"))
            playbook_matches = glob.glob(os.path.join(sops_dir, "**", f"{sop_id}.md"), recursive=True)
            self.assertEqual(len(playbook_matches), 0, "Playbook should not be committed to sops/ before human approval!")

            # Approve via Review Task
            task_id = data.get("task_id")
            app_resp = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                json={
                    "decision": "approve",
                    "reviewer": "human_reviewer@corp.com",
                    "actor_type": "human",
                },
            )
            self.assertEqual(app_resp.status_code, 200)

            # Publish
            pub_resp = self.client.post(f"/api/governance/sops/{sop_id}/publish", json={})
            self.assertEqual(pub_resp.status_code, 200)

            # NOW verify that the playbook is committed to disk!
            committed_matches = glob.glob(os.path.join(sops_dir, "**", f"{sop_id}.md"), recursive=True)
            self.assertEqual(len(committed_matches), 1, "Playbook must be committed to sops/ after human publication!")

            # Cleanup committed file
            for p in committed_matches:
                if os.path.exists(p):
                    os.remove(p)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)


if __name__ == "__main__":
    unittest.main(verbosity=2)
