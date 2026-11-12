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
import glob
import tempfile
import unittest
from starlette.testclient import TestClient

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import api.context as api_ctx
from server import app, governance_ledger, retrieval_index
from auth.models import AuthPrincipal
from auth.tokens import create_access_token
from agents.a2_structuring.canonical_builder import (
    build_canonical_sop_from_draft,
    write_canonical_sop_json,
    sync_canonical_to_playbook,
)
from utils.security import verify_playbook_before_execution
from schemas.canonical_sop_schema import validate_canonical_sop_dict


def _make_auth_header(identity: str, roles, *, tenant_id="tn_northwind", clearance="L1", actor_type="human"):
    principal = AuthPrincipal(
        sub=f"usr_{uuid.uuid4().hex[:10]}",
        identity=identity,
        display_name=identity,
        roles=roles,
        tenant_id=tenant_id,
        clearance=clearance,
        actor_type=actor_type,
        agent_id=identity if actor_type == "agent" else None,
    )
    token, _, _ = create_access_token(principal, ttl_seconds=600)
    return {"Authorization": f"Bearer {token}"}


class TestPipelineIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"
        cls.hdr_alice = _make_auth_header("alice@example.com", ["process_owner"], clearance="L1")
        cls.hdr_bob = _make_auth_header("bob@example.com", ["process_owner"], clearance="L1")
        cls.hdr_po_l2 = _make_auth_header("po_l2@example.com", ["process_owner"], clearance="L2")
        cls.hdr_charlie = _make_auth_header("charlie@example.com", ["security_reviewer"], clearance="L2")
        cls.hdr_sec_2 = _make_auth_header("sec_reviewer2@corp.com", ["security_reviewer"], clearance="L2")
        cls.hdr_admin = _make_auth_header("admin@example.com", ["admin"], clearance="L3")
        cls.hdr_agent_l1 = _make_auth_header("agent_l1", ["agent"], clearance="L1", actor_type="agent")
        cls.hdr_agent_l2 = _make_auth_header("agent_l2", ["agent"], clearance="L2", actor_type="agent")

    def setUp(self):
        self.client = TestClient(app)

    def _stage_valid_draft(
        self,
        sop_id: str,
        content_hash: str,
        *,
        title: str = "Standard Endpoint Maintenance",
        purpose: str = "Verifies endpoint service state safely.",
        level: str = "L1",
        score: int = 25,
        uploaded_by: str = "alice@example.com",
        tenant_id: str = "tn_northwind",
    ) -> str:
        raw_text = (
            f"Title: {title}\n"
            f"Purpose: {purpose}\n"
            f"Step 1: Check host date and time status\n"
        )
        draft_payload = {
            "raw_text": raw_text,
            "frontmatter": {
                "sop_id": sop_id,
                "title": title,
                "category": "system",
                "platform": "system",
                "description": purpose,
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "command",
                        "sop_step_description": "Check host date and time status",
                        "command": "Get-Date",
                        "shell": "powershell",
                        "source_quote": "Step 1: Check host date and time status",
                    }
                ],
            },
        }
        canon = build_canonical_sop_from_draft(
            draft_payload,
            raw_text=raw_text,
            tenant_id=tenant_id,
            uploaded_by=uploaded_by,
        )
        canon["sop_id"] = sop_id
        canon["tenant_id"] = tenant_id
        canon.setdefault("source", {})["file_sha256"] = content_hash
        canon.setdefault("classification", {})["level"] = level
        canon["classification"]["score"] = score
        os.makedirs(api_ctx.DRAFTS_DIR, exist_ok=True)
        path = os.path.join(api_ctx.DRAFTS_DIR, f"{sop_id}.draft.json")
        with open(path, "w", encoding="utf-8") as df:
            json.dump(
                {
                    "sop_id": sop_id,
                    "tenant_id": tenant_id,
                    "uploaded_by": uploaded_by,
                    "raw_filename": f"{sop_id.lower()}.txt",
                    "draft": draft_payload,
                    "canonical_draft": canon,
                },
                df,
                indent=2,
            )
        return path

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

        # Verify dlp_stats and is_ocr forwarding into confidentiality engine & source metadata
        canon_with_signals = build_canonical_sop_from_draft(
            mock_draft,
            raw_text="Flush Windows DNS resolver cache\nClear Chrome temporary socket pools",
            dlp_stats={"emails": 5, "passwords": 0, "api_keys": 0, "private_keys": 0},
            is_ocr=True,
        )
        self.assertTrue(canon_with_signals["source"]["ocr"])
        self.assertGreater(
            canon_with_signals["classification"]["score"],
            canonical_dict["classification"]["score"],
        )

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
        """REST APIs return tenant/clearance-filtered jobs list and review tasks with live overdue status."""
        uid = uuid.uuid4().hex[:6].upper()
        job_id = f"job_api_{uid}"
        sop_id = f"SOP-API-{uid}"
        governance_ledger.start_job(
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
        resp = self.client.get("/api/governance/jobs", headers=self.hdr_bob)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("jobs", data)
        self.assertTrue(any(j["job_id"] == job_id for j in data["jobs"]))

        # 2. GET /api/governance/review-tasks
        resp = self.client.get("/api/governance/review-tasks", headers=self.hdr_bob)
        self.assertEqual(resp.status_code, 200)
        tasks_data = resp.json()
        self.assertIn("tasks", tasks_data)
        matching_task = next((t for t in tasks_data["tasks"] if t["task_id"] == task.task_id), None)
        self.assertIsNotNone(matching_task)
        self.assertIn("is_overdue", matching_task)

    def test_04_api_record_decision_separation_of_duties_enforced(self):
        """Option A blocks process_owner/admin from /decision (403) and enforces SoD for security_reviewer."""
        uid = uuid.uuid4().hex[:6].upper()
        job_id = f"job_sod_{uid}"
        sop_id = f"SOP-SOD-{uid}"
        draft_1 = self._stage_valid_draft(sop_id, f"hash_sod_{uid}", level="L0", score=10, uploaded_by="alice@example.com")
        governance_ledger.start_job(
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

        # Option A: process_owner (uploader or non-uploader) and admin cannot decide review tasks
        for forbidden_hdr in (self.hdr_alice, self.hdr_bob, self.hdr_admin):
            r_role = self.client.post(
                f"/api/governance/review-tasks/{task.task_id}/decision",
                headers=forbidden_hdr,
                json={"decision": "approve", "reviewer": "sec_reviewer2@corp.com", "actor_type": "human", "confirmed_classification": True},
            )
            self.assertEqual(r_role.status_code, 403)
            self.assertEqual(r_role.json().get("error_code"), "insufficient_role")

        # Defense-in-depth SoD: a security_reviewer matching uploaded_by is blocked with 403 separation_of_duties
        job_id_2 = f"job_sod2_{uid}"
        sop_id_2 = f"SOP-SOD2-{uid}"
        draft_2 = self._stage_valid_draft(sop_id_2, f"hash_sod2_{uid}", level="L0", score=10, uploaded_by="charlie@example.com")
        try:
            governance_ledger.start_job(
                job_id=job_id_2,
                sop_id=sop_id_2,
                tenant_id="tn_northwind",
                content_sha256=f"hash_sod2_{uid}",
                uploaded_by="charlie@example.com",
            )
            governance_ledger.transition_state(job_id_2, "extracting")
            governance_ledger.transition_state(job_id_2, "scanning")
            governance_ledger.transition_state(job_id_2, "structuring")
            governance_ledger.transition_state(job_id_2, "assessing")
            task_2 = governance_ledger.create_review_task(job_id_2, 20, "L0")

            resp_sod = self.client.post(
                f"/api/governance/review-tasks/{task_2.task_id}/decision",
                headers=self.hdr_charlie,
                json={"decision": "approve", "reviewer": "sec_reviewer2@corp.com", "actor_type": "human", "confirmed_classification": True},
            )
            self.assertEqual(resp_sod.status_code, 403)
            self.assertEqual(resp_sod.json().get("error_code"), "separation_of_duties")

            # Independent Security Reviewer approves -> 200 Success, stamped with token identity
            resp = self.client.post(
                f"/api/governance/review-tasks/{task.task_id}/decision",
                headers=self.hdr_charlie,
                json={
                    "decision": "approve",
                    "confirmed_classification": True,
                },
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json().get("job_state"), "approved")
            self.assertEqual(resp.json().get("reviewer"), "charlie@example.com")
        finally:
            for p in (draft_1, draft_2):
                if os.path.exists(p):
                    os.remove(p)

    def test_05_api_publish_and_downstream_search(self):
        """Approved SOP publishes strictly from stored draft and becomes searchable by token clearance."""
        uid = uuid.uuid4().hex[:6].upper()
        job_id = f"job_pub_{uid}"
        sop_id = f"SOP-PUB-{uid}"
        content_hash = f"hash_pub_{uid}"
        draft_path = self._stage_valid_draft(
            sop_id,
            content_hash,
            title=f"Secure Secret Storage Configuration {uid}",
            purpose=f"Configures enterprise vault tokens {uid}.",
            level="L2",
            score=55,
            uploaded_by="alice@example.com",
        )
        sops_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "sops"))
        try:
            governance_ledger.start_job(
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
            task = governance_ledger.create_review_task(job_id, 55, "L2")  # L2 Confidential -> Security reviewer

            # Security reviewer Charlie (L2) approves with explicit confirmation
            dec_resp = self.client.post(
                f"/api/governance/review-tasks/{task.task_id}/decision",
                headers=self.hdr_charlie,
                json={"decision": "approve", "confirmed_classification": True},
            )
            self.assertEqual(dec_resp.status_code, 200, dec_resp.text)

            # Body canonical_sop (e.g. L0 downgrade or forged title) MUST be ignored (C4)
            forged_body = {
                "canonical_sop": {
                    "sop_id": sop_id,
                    "title": f"Forged Public Override {uid}",
                    "classification": {"level": "L0", "score": 5},
                }
            }
            # Option A: security_reviewer and admin cannot publish; L1 process_owner blocked by L2 stored clearance; L2 process_owner succeeds
            self.assertEqual(
                self.client.post(f"/api/governance/sops/{sop_id}/publish", headers=self.hdr_charlie, json=forged_body).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(f"/api/governance/sops/{sop_id}/publish", headers=self.hdr_admin, json=forged_body).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(f"/api/governance/sops/{sop_id}/publish", headers=self.hdr_alice, json=forged_body).status_code,
                403,
            )

            resp = self.client.post(
                f"/api/governance/sops/{sop_id}/publish",
                headers=self.hdr_po_l2,
                json=forged_body,
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()
            self.assertEqual(data.get("status"), "published")
            self.assertTrue(data.get("citation").startswith(f"{sop_id}@v1#"))

            # Test Downstream Search: L1 agent cannot see L2 SOP even if spoofing clearance_level=L2 in body
            resp_l1 = self.client.post(
                "/api/governance/downstream/search",
                headers=self.hdr_agent_l1,
                json={
                    "query": f"vault tokens {uid}",
                    "tenant_id": "tn_northwind",
                    "clearance_level": "L2",
                },
            )
            self.assertEqual(resp_l1.status_code, 200)
            returned_l1_ids = {r["sop_id"] for r in resp_l1.json()["results"]}
            self.assertNotIn(sop_id, returned_l1_ids)
            self.assertEqual(resp_l1.json().get("caller_clearance"), "L1")

            # Test Downstream Search: L2 agent CAN see L2 SOP from stored approved draft
            resp_l2 = self.client.post(
                "/api/governance/downstream/search",
                headers=self.hdr_agent_l2,
                json={"query": f"vault tokens {uid}"},
            )
            self.assertEqual(resp_l2.status_code, 200)
            returned_l2_ids = {r["sop_id"] for r in resp_l2.json()["results"]}
            self.assertIn(sop_id, returned_l2_ids)
        finally:
            if os.path.exists(draft_path):
                os.remove(draft_path)
            for pattern in (f"{sop_id}.md", f"{sop_id}.canonical.json"):
                for p in glob.glob(os.path.join(sops_dir, "**", pattern), recursive=True):
                    if os.path.exists(p):
                        os.remove(p)

    def test_06_human_in_the_loop_before_saving(self):
        """Ingestion creates review task and halts at awaiting_review without saving to sops/."""
        from unittest.mock import patch
        uid = uuid.uuid4().hex[:6].upper()
        sop_id = f"SOP-TEST-{uid}"
        filename = f"test_sop_{uid}.txt"
        uploads_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "_uploads", "tn_northwind")
        )
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

        sops_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base", "sops"))
        try:
            with patch("api.routes_ingestion.jit_converter.plan_okf_from_raw", return_value=mock_draft):
                resp = self.client.post(
                    "/api/uploads/ingest",
                    headers=self.hdr_alice,
                    json={"filename": filename, "sop_id": sop_id},
                )
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()
            self.assertEqual(data.get("status"), "awaiting_review")
            self.assertIn("task_id", data)
            self.assertEqual(data.get("uploaded_by"), "alice@example.com")
            self.assertEqual(data.get("sop_id"), sop_id)

            # Check that the playbook was NOT saved to sops/ yet!
            playbook_matches = glob.glob(os.path.join(sops_dir, "**", f"{sop_id}.md"), recursive=True)
            self.assertEqual(len(playbook_matches), 0, "Playbook should not be committed to sops/ before human approval!")

            # Approve via Review Task using independent Security Reviewer token
            task_id = data.get("task_id")
            app_resp = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers=self.hdr_charlie,
                json={"decision": "approve", "confirmed_classification": True},
            )
            self.assertEqual(app_resp.status_code, 200, app_resp.text)

            # Security Reviewer cannot publish; Process Owner publishes
            self.assertEqual(
                self.client.post(f"/api/governance/sops/{sop_id}/publish", headers=self.hdr_charlie, json={}).status_code,
                403,
            )
            pub_resp = self.client.post(
                f"/api/governance/sops/{sop_id}/publish",
                headers=self.hdr_alice,
                json={},
            )
            self.assertEqual(pub_resp.status_code, 200, pub_resp.text)

            # NOW verify that the playbook is committed to disk!
            committed_matches = glob.glob(os.path.join(sops_dir, "**", f"{sop_id}.md"), recursive=True)
            self.assertEqual(len(committed_matches), 1, "Playbook must be committed to sops/ after human publication!")
        finally:
            for pattern in (f"{sop_id}.md", f"{sop_id}.canonical.json"):
                for p in glob.glob(os.path.join(sops_dir, "**", pattern), recursive=True):
                    if os.path.exists(p):
                        os.remove(p)
            if os.path.exists(filepath):
                os.remove(filepath)


if __name__ == "__main__":
    unittest.main(verbosity=2)
