"""
Regression tests for:
1. Triage Router `confidentiality_advisory` parsing & `plan_okf_from_raw` / `canonical_builder` wiring
2. VLM screenshot observation scanning during deterministic confidentiality scoring
3. Security Reviewer tier adjustment & rule-vs-AI conflict resolution (anti-downgrade & clearance gates)
"""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft  # noqa: E402
from agents.a2_structuring.triage_router import run_triage_router  # noqa: E402
from auth.models import (  # noqa: E402
    AuthPrincipal,
    ROLE_PROCESS_OWNER,
    ROLE_SECURITY_REVIEWER,
)
from auth.tokens import create_access_token  # noqa: E402
from schemas.governance_models import JobRecord  # noqa: E402


def _tok(identity: str, roles, tenant_id: str, clearance: str = "L3") -> str:
    principal = AuthPrincipal(
        sub=identity,
        identity=identity,
        display_name=identity,
        roles=tuple(roles),
        tenant_id=tenant_id,
        clearance=clearance,
        actor_type="human",
    )
    tok, _, _ = create_access_token(principal)
    return tok


def _sample_canonical_and_draft(sop_id: str, level: str = "L0", rule_level: str = "L0", ai_level: str = "L0", conflict: bool = False):
    raw_text = "Step 1: Verify network adapter status using Get-NetAdapter"
    fm = {
        "sop_id": sop_id,
        "title": "Sample Network Verification",
        "category": "network",
        "platform": "system",
        "target_os": "windows",
        "steps": [
            {
                "step_number": 1,
                "step_type": "command",
                "shell": "powershell",
                "sop_step_description": "Verify network adapter status using Get-NetAdapter",
                "command": "Get-NetAdapter",
                "source_quote": "Step 1: Verify network adapter status using Get-NetAdapter",
                "parse_instruction": "Verify adapter list",
                "fallback_command": "ipconfig /all",
            }
        ],
    }
    draft = {
        "sop_id": sop_id,
        "frontmatter": fm,
        "raw_text": raw_text,
        "vlm_reports": [],
    }
    canon = build_canonical_sop_from_draft(
        draft,
        raw_text=raw_text,
        tenant_id="tn_test_conf",
        uploaded_by="owner@test.example",
    )
    score_map = {"L0": 5, "L1": 25, "L2": 55, "L3": 80}
    canon["classification"].update({
        "level": level,
        "score": score_map[level],
        "rule_level": rule_level,
        "ai_suggested_level": ai_level,
        "conflict": conflict,
    })
    return raw_text, draft, canon


class TestTriageAdvisoryAndCanonicalWiring(unittest.TestCase):
    def test_triage_router_returns_sanitized_confidentiality_advisory(self):
        fake_llm = SimpleNamespace(
            invoke=lambda _msgs: SimpleNamespace(
                content=json.dumps({
                    "classification": "command",
                    "target_os": "windows",
                    "detected_platforms": [],
                    "requires_shell": True,
                    "is_executable": True,
                    "confidence_score": 0.96,
                    "confidence_level": "High",
                    "confidence_reason": "Native Windows VPN commands",
                    "triage_summary": "Configure internal VPN profile",
                    "confidentiality_advisory": {
                        "security_controls": True,
                        "customer_data": False,
                        "legal_financial": False,
                        "proprietary_process": True,
                        "suggested_level": "L1",
                        "rationale": "Internal company VPN & RDP setup SOP",
                    },
                }),
                usage_metadata={"input_tokens": 50, "output_tokens": 30},
            )
        )
        with patch("agents.a2_structuring.triage_router.get_llm", return_value=fake_llm), patch(
            "gemini_monitor.monitor.check_daily_limit"
        ), patch("gemini_monitor.monitor.record_call"):
            res = run_triage_router("Connect to vpn.airretailer.corp", "SOP-ARVPN", enable_tool_inspection=False)

        adv = res["confidentiality_advisory"]
        self.assertTrue(adv["security_controls"])
        self.assertTrue(adv["proprietary_process"])
        self.assertFalse(adv["customer_data"])
        self.assertEqual(adv["suggested_level"], "L1")
        self.assertIn("VPN", adv["rationale"])

    def test_canonical_builder_scans_vlm_text_and_consumes_draft_ai_advisory(self):
        raw_text = "Step 1: Open the AirRetailer VPN client on Windows"
        draft = {
            "sop_id": "SOP-ARVPN",
            "frontmatter": {
                "sop_id": "SOP-ARVPN",
                "title": "AirRetailer VPN Setup",
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "command",
                        "shell": "powershell",
                        "sop_step_description": "Open AirRetailer VPN client",
                        "command": "rasdial AirRetailerVPN",
                        "source_quote": "Open the AirRetailer VPN client",
                    }
                ],
            },
            "ai_advisory": {
                "security_controls": True,
                "customer_data": False,
                "legal_financial": False,
                "proprietary_process": True,
                "suggested_level": "L1",
                "rationale": "Internal corporate VPN configuration SOP",
            },
        }
        vlm_reports = [
            {
                "image_index": 1,
                "label": "Image 1",
                "anchor_line": 1,
                "report_text": "Screenshot shows portal url vpn.airretailer.corp and internal IP 10.20.30.40.",
            }
        ]
        canon = build_canonical_sop_from_draft(
            draft,
            raw_text=raw_text,
            tenant_id="tn_test",
            uploaded_by="owner@test.example",
            vlm_reports=vlm_reports,
        )
        cl = canon["classification"]
        # 5 base + 15 (2 internal infra items from VLM!) + 15 security_controls + 10 proprietary_process = 45 -> L1
        self.assertEqual(cl["level"], "L1")
        self.assertEqual(cl["rule_level"], "L1")
        self.assertEqual(cl["ai_suggested_level"], "L1")
        self.assertFalse(cl["conflict"])
        self.assertGreaterEqual(cl["score"], 40)
        self.assertIn("internal_infrastructure", cl["evidence_categories"])
        self.assertIn("security_controls", cl["evidence_categories"])


class TestReviewerTierOverrideAndConflictResolution(unittest.TestCase):
    def setUp(self):
        from server import app
        from api import context as api_ctx

        self.client = TestClient(app)
        self.api_ctx = api_ctx
        self.ledger = api_ctx.governance_ledger
        self._orig_jobs = dict(self.ledger._jobs)
        self._orig_drafts_dir = api_ctx.DRAFTS_DIR
        self._tmp = tempfile.TemporaryDirectory()
        self._drafts_dir = os.path.join(self._tmp.name, "_drafts")
        os.makedirs(self._drafts_dir, exist_ok=True)
        api_ctx.DRAFTS_DIR = self._drafts_dir

        import api.routes_governance as rg
        self._rg = rg
        self._orig_rg_drafts = rg.DRAFTS_DIR
        rg.DRAFTS_DIR = self._drafts_dir

    def tearDown(self):
        self.ledger._jobs.clear()
        self.ledger._jobs.update(self._orig_jobs)
        self.api_ctx.DRAFTS_DIR = self._orig_drafts_dir
        self._rg.DRAFTS_DIR = self._orig_rg_drafts
        self._tmp.cleanup()

    def _seed_pending_task(self, job_id: str, sop_id: str, level: str = "L0", rule_level: str = "L0", ai_level: str = "L0", conflict: bool = False):
        import hashlib
        raw_text, draft, canon = _sample_canonical_and_draft(sop_id, level=level, rule_level=rule_level, ai_level=ai_level, conflict=conflict)
        file_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        canon["source"]["file_sha256"] = file_sha
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            self.ledger._jobs.pop(job_id, None)
            self.ledger.start_job(
                job_id=job_id,
                sop_id=sop_id,
                tenant_id="tn_test_conf",
                content_sha256=file_sha,
                uploaded_by="owner@test.example",
                allow_supersede=True,
            )
            self.ledger.transition_state(job_id, "extracting")
            self.ledger.transition_state(job_id, "scanning")
            self.ledger.transition_state(job_id, "structuring")
            self.ledger.transition_state(job_id, "assessing")
            task = self.ledger.create_review_task(
                job_id=job_id,
                confidentiality_score=canon["classification"]["score"],
                confidentiality_level=canon["classification"]["level"],
            )
        draft_path = os.path.join(self._drafts_dir, f"{sop_id}.draft.json")
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "sop_id": sop_id,
                    "raw_filename": f"{sop_id}.txt",
                    "raw_text": raw_text,
                    "draft": draft,
                    "canonical_draft": canon,
                },
                f,
                indent=2,
            )
        return task.task_id, draft_path

    def test_reviewer_can_upgrade_l0_to_l1_and_anti_downgrade_holds(self):
        task_id, draft_path = self._seed_pending_task("job_up_1", "SOP-UPGRADE1", level="L0", rule_level="L0", ai_level="L0")
        tok_sec = _tok("sec@test.example", [ROLE_SECURITY_REVIEWER], "tn_test_conf", clearance="L3")
        hdrs = {"Authorization": f"Bearer {tok_sec}"}

        # Changing tier without a reason is rejected (422)
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            r_no_reason = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers=hdrs,
                json={"decision": "approve", "confirmed_classification": True, "adjusted_level": "L1"},
            )
        self.assertEqual(r_no_reason.status_code, 422)

        # Low-clearance reviewer (L1) cannot promote to L2 (403)
        tok_sec_l1 = _tok("sec_l1@test.example", [ROLE_SECURITY_REVIEWER], "tn_test_conf", clearance="L1")
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            r_too_high = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers={"Authorization": f"Bearer {tok_sec_l1}"},
                json={
                    "decision": "approve",
                    "confirmed_classification": True,
                    "adjusted_level": "L2",
                    "override_reason": "Should fail clearance check",
                },
            )
        self.assertEqual(r_too_high.status_code, 403)

        # Valid upgrade L0 -> L1 with reason passes all gates and updates canonical draft
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            r_ok = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers=hdrs,
                json={
                    "decision": "approve",
                    "confirmed_classification": True,
                    "adjusted_level": "L1",
                    "override_reason": "Internal VPN/RDP procedure requires L1",
                },
            )
        self.assertEqual(r_ok.status_code, 200, r_ok.text)
        with open(draft_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        cl = saved["canonical_draft"]["classification"]
        self.assertEqual(cl["level"], "L1")
        self.assertGreaterEqual(cl["score"], 21)
        self.assertTrue(cl["confirmed"])
        self.assertEqual(cl["override_reason"], "Internal VPN/RDP procedure requires L1")

    def test_reviewer_cannot_downgrade_below_rule_level_but_can_resolve_ai_conflict(self):
        # Task where rule_level=L1, ai_suggested_level=L2, conflict=True
        task_id, _ = self._seed_pending_task("job_conf_1", "SOP-CONF1", level="L2", rule_level="L1", ai_level="L2", conflict=True)
        tok_sec = _tok("sec@test.example", [ROLE_SECURITY_REVIEWER], "tn_test_conf", clearance="L3")
        hdrs = {"Authorization": f"Bearer {tok_sec}"}

        # Cannot downgrade below rule_level L1 -> L0 (422)
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            r_down = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers=hdrs,
                json={
                    "decision": "approve",
                    "confirmed_classification": True,
                    "adjusted_level": "L0",
                    "override_reason": "Try downgrade below rule floor",
                },
            )
        self.assertEqual(r_down.status_code, 422)

        # Unresolved conflict without override still fails Gate 5 (400 GateFailureError)
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            r_unres = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers=hdrs,
                json={"decision": "approve", "confirmed_classification": True},
            )
        self.assertEqual(r_unres.status_code, 400)
        self.assertIn("Gate 5", r_unres.text)

        # Resolving conflict to L1 (>= rule_level) with override_reason passes Gate 5 & Gate 6
        with patch.object(self.ledger, "_save_unlocked", lambda: None):
            r_res = self.client.post(
                f"/api/governance/review-tasks/{task_id}/decision",
                headers=hdrs,
                json={
                    "decision": "approve",
                    "confirmed_classification": True,
                    "adjusted_level": "L1",
                    "override_reason": "Verified internal-only procedure; L1 is sufficient",
                },
            )
        self.assertEqual(r_res.status_code, 200, r_res.text)


if __name__ == "__main__":
    unittest.main()

