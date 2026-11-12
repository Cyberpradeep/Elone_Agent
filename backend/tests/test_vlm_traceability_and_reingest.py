"""
Regression & Integration Suite for:
1. Multi-Modal VLM Quote Traceability & Media Provenance
2. CLI Agent Protocol A2/A4/A6 Alignment
3. Ledger Supersede & FastAPI Re-Ingestion Lifecycle
"""

import os
import sys
import copy
import json
import uuid
import shutil
import hashlib
import tempfile
import unittest
import subprocess
from unittest.mock import patch, MagicMock

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ---------------------------------------------------------------------------
# 1. Quote Tracer & VLM Visual Inspection Verification
# ---------------------------------------------------------------------------

class TestVlmQuoteVerification(unittest.TestCase):
    def setUp(self):
        self.raw_lines = [
            "AirRetailer VPN & RDP Setup Procedure",
            "1. Open https://securevpn.airretailer.com in browser",
            "2. Download and install Cisco AnyConnect client",
            "3. Launch Remote Desktop Connection from Start menu",
        ]
        self.vlm_reports = [
            {
                "image_index": 12,
                "label": "Image 12",
                "image_path": "knowledge_base/images/img_12.png",
                "report_path": "knowledge_base/reports/img_12.md",
                "confidence_score": 0.95,
                "confidence_level": "High",
                "anchor_line": 4,
                "report_text": (
                    "SCREEN / CONTEXT: Office PC Configuration Modal\n"
                    "UI ACTION: Click the 'Save' button to confirm PC configuration changes\n"
                    "VISIBLE ENTITIES: IP Address field, Username: airretailer.local\\jithin-vz\n"
                    "CONFIDENCE SCORE: 0.95\n"
                    "CONFIDENCE LEVEL: High\n"
                    "CONFIDENCE REASON: Crisp crisp screenshot text\n"
                ),
            },
            {
                "image_index": 13,
                "label": "Image 13",
                "confidence_score": 0.84,
                "confidence_level": "Medium",
                "anchor_line": 4,
                "report_text": (
                    "SCREEN / CONTEXT: Medium Confidence Window\n"
                    "UI ACTION: Click medium confidence apply button now\n"
                    "CONFIDENCE SCORE: 0.84\n"
                    "CONFIDENCE LEVEL: Medium\n"
                ),
            },
            {
                "image_index": 14,
                "label": "Image 14",
                "confidence_score": 0.45,
                "confidence_level": "Low",
                "anchor_line": 4,
                "report_text": (
                    "SCREEN / CONTEXT: Blurry Window\n"
                    "UI ACTION: Click the Connect button in blurry popup\n"
                    "CONFIDENCE SCORE: 0.45\n"
                    "CONFIDENCE LEVEL: Low\n"
                ),
            },
            {
                "image_index": 15,
                "label": "Image 15",
                "confidence_score": 0.85,
                "confidence_level": "High",
                "anchor_line": 4,
                "report_text": (
                    "SCREEN / CONTEXT: Boundary High Confidence Panel\n"
                    "UI ACTION: Select the Enable Split Tunneling checkbox\n"
                    "CONFIDENCE SCORE: 0.85\n"
                ),
            },
        ]

    def test_high_confidence_vlm_quote_match_and_threshold(self):
        from agents.a4_verification.quote_tracer import verify_quote_against_vlm_reports

        ok, rep = verify_quote_against_vlm_reports(
            self.vlm_reports,
            "Click the 'Save' button to confirm PC configuration changes",
        )
        self.assertTrue(ok)
        self.assertIsNotNone(rep)
        self.assertEqual(rep["label"], "Image 12")

        # Boundary 0.85 must pass
        ok_boundary, rep_boundary = verify_quote_against_vlm_reports(
            self.vlm_reports,
            "Select the Enable Split Tunneling checkbox",
        )
        self.assertTrue(ok_boundary)
        self.assertEqual(rep_boundary["label"], "Image 15")

        # Confidence < 0.85 (0.84 and 0.45) must fail even on exact literal match
        ok_med, _ = verify_quote_against_vlm_reports(
            self.vlm_reports,
            "Click medium confidence apply button now",
        )
        self.assertFalse(ok_med)

        ok_low, _ = verify_quote_against_vlm_reports(
            self.vlm_reports,
            "Click the Connect button in blurry popup",
        )
        self.assertFalse(ok_low)

    def test_confidence_metadata_lines_and_paraphrases_rejected(self):
        from agents.a4_verification.quote_tracer import verify_quote_against_vlm_reports

        for forbidden_quote in (
            "CONFIDENCE SCORE: 0.95",
            "CONFIDENCE LEVEL: High",
            "Crisp crisp screenshot text",
            "Click the Save button on the remote gateway dialog",
        ):
            ok, _ = verify_quote_against_vlm_reports(self.vlm_reports, forbidden_quote)
            self.assertFalse(ok, f"Should reject quote: {forbidden_quote}")

    def test_tier1_document_precedence_and_idempotent_reverification(self):
        from agents.a4_verification.quote_tracer import verify_canonical_quotes

        items = [
            {
                "n": 1,
                "action": "Open VPN portal",
                "source_lines": [2, 2],
                "quote": "Open https://securevpn.airretailer.com in browser",
            },
            {
                "n": 2,
                "action": "Save office PC configuration",
                "source_lines": [3, 4],  # Does not exist in written lines
                "quote": "Click the 'Save' button to confirm PC configuration changes",
            },
        ]
        total, verified, unverified = verify_canonical_quotes(
            items,
            self.raw_lines,
            vlm_reports=self.vlm_reports,
        )
        self.assertEqual(total, 2)
        self.assertEqual(verified, 2)
        self.assertEqual(unverified, [])
        self.assertTrue(items[0]["verified"])
        self.assertEqual(items[0]["evidence_source"], "document")
        self.assertNotIn("image_ref", items[0])

        self.assertTrue(items[1]["verified"])
        self.assertEqual(items[1]["evidence_source"], "visual_inspection")
        self.assertEqual(items[1]["source_lines"], [])
        self.assertEqual(items[1]["image_ref"], "Image 12")

        # Re-run on already-verified visual_inspection item (source_lines == []) must remain idempotent
        total2, verified2, unverified2 = verify_canonical_quotes(
            items,
            self.raw_lines,
            vlm_reports=self.vlm_reports,
        )
        self.assertEqual((total2, verified2, unverified2), (2, 2, []))
        self.assertEqual(items[1]["evidence_source"], "visual_inspection")
        self.assertEqual(items[1]["image_ref"], "Image 12")

        # Edit screenshot quote to non-existent text -> must fail and strip stale image_ref
        items[1]["quote"] = "Hallucinated non-existent button click"
        total3, verified3, unverified3 = verify_canonical_quotes(
            items,
            self.raw_lines,
            vlm_reports=self.vlm_reports,
        )
        self.assertEqual(total3, 2)
        self.assertEqual(verified3, 1)
        self.assertEqual(len(unverified3), 1)
        self.assertFalse(items[1]["verified"])
        self.assertEqual(items[1]["evidence_source"], "document")
        self.assertNotIn("image_ref", items[1])

    def test_compute_source_line_coverage_skips_visual_inspection_ranges(self):
        from agents.a4_verification.quote_tracer import compute_source_line_coverage

        raw_lines = [
            "Unreferenced first written prose alpha line",
            "Second unreferenced prose beta line",
        ]
        # Synthetic source_lines=[1, 1] on visual_inspection step must NOT auto-mark line 1 via range
        steps = [
            {
                "n": 1,
                "action": "Save dialog button",
                "quote": "Save dialog",
                "source_lines": [1, 1],
                "evidence_source": "visual_inspection",
            }
        ]
        total_nb, mapped_count, mapped_indices = compute_source_line_coverage(raw_lines, steps)
        self.assertEqual(total_nb, 2)
        self.assertEqual(mapped_count, 0)
        self.assertEqual(mapped_indices, [])


# ---------------------------------------------------------------------------
# 2. Prompts & Canonical Schema Contracts
# ---------------------------------------------------------------------------

class TestPromptsAndCanonicalSchema(unittest.TestCase):
    def test_all_jit_prompts_format_and_contain_vlm_mandate(self):
        from prompts.jit_converter_prompts import (
            COMMAND_COT_PROMPT,
            TOOL_COT_PROMPT,
            HYBRID_COT_PROMPT,
            JIT_COT_CONVERTER_PROMPT,
        )
        from prompts.validator_prompts import JIT_VALIDATOR_COT_SYSTEM_PROMPT

        for name, tmpl in (
            ("COMMAND_COT_PROMPT", COMMAND_COT_PROMPT),
            ("TOOL_COT_PROMPT", TOOL_COT_PROMPT),
            ("HYBRID_COT_PROMPT", HYBRID_COT_PROMPT),
        ):
            rendered = tmpl.replace("{raw_sop_text}", "SAMPLE_RAW_TEXT")
            self.assertIn("SAMPLE_RAW_TEXT", rendered, name)
            self.assertIn("Visual Inspection Report", rendered, name)
            self.assertIn("HIGH CONFIDENCE", rendered, name)
            self.assertIn("UI ACTION:", rendered, name)
            self.assertIn("MEDIUM CONFIDENCE", rendered, name)

        rendered_jit = JIT_COT_CONVERTER_PROMPT.format(
            available_tools_summary="TOOL_SUMMARY",
            raw_sop_text="JIT_RAW_TEXT",
        )
        self.assertIn("JIT_RAW_TEXT", rendered_jit)
        self.assertIn("Visual Inspection Report", rendered_jit)
        self.assertIn("HIGH CONFIDENCE", rendered_jit)
        self.assertNotIn('{{\n    "sop_id":', rendered_jit)

        self.assertIn("Visual Inspection Report", JIT_VALIDATOR_COT_SYSTEM_PROMPT)
        self.assertIn("HIGH CONFIDENCE", JIT_VALIDATOR_COT_SYSTEM_PROMPT)

    def test_canonical_schema_supports_vlm_provenance_and_file_sha256(self):
        from schemas.canonical_sop_schema import validate_canonical_sop_dict

        payload = {
            "schema_version": "1.0",
            "sop_id": "SOP-VLM-01",
            "version": 1,
            "tenant_id": "tn_northwind",
            "title": "VPN Setup",
            "source": {
                "filename": "vpn.docx",
                "sha256": "a" * 64,
                "file_sha256": "b" * 64,
                "size": 120,
                "detected_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "pages": 1,
                "extracted_lines": 5,
            },
            "steps": [
                {
                    "n": 1,
                    "action": "Click Save button",
                    "source_lines": [],
                    "quote": "Click the 'Save' button to confirm PC configuration changes",
                    "verified": True,
                    "evidence_source": "visual_inspection",
                    "image_ref": "Image 12",
                }
            ],
            "media": [
                {
                    "label": "Image 12",
                    "description": "UI ACTION: Click the 'Save' button",
                    "source_line": 4,
                    "image_path": "img_12.png",
                    "report_path": "img_12.md",
                    "confidence_score": 0.95,
                    "confidence_level": "High",
                }
            ],
            "lifecycle": {
                "state": "awaiting_review",
                "uploaded_by": "analyst@example.com",
                "created_at": "2026-11-11T00:00:00+00:00",
            },
            "provenance": {
                "producing_agent": "A2_structuring",
                "generated_at": "2026-11-11T00:00:00+00:00",
            },
        }
        valid, errors, model = validate_canonical_sop_dict(payload)
        self.assertTrue(valid, f"Schema validation failed: {errors}")
        self.assertEqual(model.source.file_sha256, "b" * 64)
        self.assertEqual(model.steps[0].evidence_source, "visual_inspection")
        self.assertEqual(model.steps[0].image_ref, "Image 12")
        self.assertEqual(model.media[0].confidence_score, 0.95)


# ---------------------------------------------------------------------------
# 3. Canonical Builder & OKF Builder VLM Isolation & Provenance
# ---------------------------------------------------------------------------

class TestCanonicalBuilderAndOkfVlm(unittest.TestCase):
    def test_written_text_isolation_and_okf_dual_export_vlm_media(self):
        import agents.a2_structuring.canonical_builder as canonical_builder
        import agents.a2_structuring.okf_builder as okf_builder
        from agents.a3_security.confidentiality_engine import compute_confidentiality_score
        from schemas.canonical_sop_schema import validate_canonical_sop_dict

        raw_text = (
            "AirRetailer VPN Connection Guide\n"
            "Open https://securevpn.airretailer.com\n"
            "Launch Remote Desktop Connection\n"
            "Save office PC profile"
        )
        # Deliberately put a sensitive keyword ('internal salary payroll') ONLY in VLM report
        # to verify confidentiality and source hashes remain isolated to written raw_text.
        vlm_reports = [
            {
                "image_index": 12,
                "label": "Image 12",
                "image_path": "kb/img_12.png",
                "report_path": "kb/img_12.md",
                "confidence_score": 0.95,
                "confidence_level": "High",
                "anchor_line": 4,
                "report_text": (
                    "SCREEN / CONTEXT: Office PC Modal\n"
                    "UI ACTION: Click the 'Save' button to confirm PC configuration changes\n"
                    "VISIBLE ENTITIES: internal salary payroll token note\n"
                    "CONFIDENCE SCORE: 0.95\n"
                ),
            }
        ]
        draft = {
            "sop_id": "SOP-VLM-ISO-01",
            "raw_text": raw_text,
            "vlm_reports": vlm_reports,
            "frontmatter": {
                "sop_id": "SOP-VLM-ISO-01",
                "title": "AirRetailer VPN Setup",
                "category": "network",
                "description": "Configure VPN and Remote Desktop.",
                "steps": [
                    {
                        "step_number": 1,
                        "sop_step_description": "Open AirRetailer VPN portal in browser",
                        "step_type": "command",
                        "command": "start https://securevpn.airretailer.com",
                        "source_quote": "Open https://securevpn.airretailer.com",
                    },
                    {
                        "step_number": 2,
                        "sop_step_description": "Save office PC profile",
                        "step_type": "command",
                        "command": "save-rdp-profile",
                        "source_quote": "Click the 'Save' button to confirm PC configuration changes",
                    },
                ],
            },
        }

        canon = canonical_builder.build_canonical_sop_from_draft(
            draft,
            raw_text=raw_text,
            vlm_reports=vlm_reports,
        )
        valid, errors, _ = validate_canonical_sop_dict(canon)
        self.assertTrue(valid, f"Schema validation errors: {errors}")

        # Written text isolation
        self.assertEqual(canon["source"]["sha256"], hashlib.sha256(raw_text.encode("utf-8")).hexdigest())
        self.assertEqual(canon["source"]["size"], len(raw_text.encode("utf-8")))
        expected_conf = compute_confidentiality_score(raw_text)
        self.assertEqual(canon["classification"]["score"], expected_conf["score"])

        # Step quote verification & provenance
        self.assertEqual(canon["steps"][0]["evidence_source"], "document")
        self.assertTrue(canon["steps"][0]["verified"])
        self.assertEqual(canon["steps"][1]["evidence_source"], "visual_inspection")
        self.assertTrue(canon["steps"][1]["verified"])
        self.assertEqual(canon["steps"][1]["image_ref"], "Image 12")
        self.assertEqual(canon["steps"][1]["source_lines"], [])
        self.assertEqual(len(canon["media"]), 1)
        self.assertEqual(canon["media"][0]["source_line"], 4)
        self.assertEqual(canon["media"][0]["confidence_score"], 0.95)

        # Dual export via write_okf_playbook preserves media + screenshot verified=True
        with tempfile.TemporaryDirectory() as tmpdir:
            sops_dir = os.path.join(tmpdir, "sops")
            patterns_dir = os.path.join(tmpdir, "patterns")
            logs_dir = os.path.join(tmpdir, "logs")
            index_path = os.path.join(sops_dir, "index.md")
            os.makedirs(sops_dir, exist_ok=True)
            with patch.multiple(
                okf_builder,
                SOPS_DIR=sops_dir,
                PATTERNS_DIR=patterns_dir,
                LOGS_DIR=logs_dir,
                INDEX_PATH=index_path,
            ), patch.object(canonical_builder, "SOPS_DIR", sops_dir):
                md_path = okf_builder.write_okf_playbook(copy.deepcopy(draft), raw_filename="vpn.docx")
                self.assertTrue(os.path.exists(md_path))
                canon_path = os.path.join(sops_dir, "network", "SOP-VLM-ISO-01.canonical.json")
                self.assertTrue(os.path.exists(canon_path))
                with open(canon_path, "r", encoding="utf-8") as cf:
                    saved_canon = json.load(cf)
                self.assertEqual(len(saved_canon["media"]), 1)
                self.assertTrue(saved_canon["steps"][1]["verified"])
                self.assertEqual(saved_canon["steps"][1]["evidence_source"], "visual_inspection")


# ---------------------------------------------------------------------------
# 4. Execution Planner & Orchestrator A2/A4/A6 Alignment
# ---------------------------------------------------------------------------

class TestExecutionPlannerAndOrchestratorAlignment(unittest.TestCase):
    def test_plan_okf_from_raw_vlm_anchor_override_sop_id_and_enriched_validation(self):
        import agents.a2_structuring.execution_planner as ep

        segments = [
            {"type": "text", "content": "Line one prose\nLine two prose"},
            {"type": "image", "label": "Image 1", "bytes": b"png1", "mime_type": "image/png"},
            {"type": "text", "content": "Line three prose"},
            {"type": "image", "label": "Image 2", "bytes": b"png2", "mime_type": "image/png"},
        ]

        def fake_analyze(img_bytes, mime_type, label, slug, image_index):
            return (
                f"SCREEN / CONTEXT: Screen {image_index}\nUI ACTION: Click Button {image_index}\nCONFIDENCE SCORE: 0.96",
                {
                    "image_index": image_index,
                    "label": label,
                    "image_path": f"img_{image_index}.png",
                    "file_path": f"rep_{image_index}.md",
                    "confidence_score": 0.96,
                    "confidence_level": "High",
                },
            )

        captured_validation_inputs = []

        def fake_validate(source_text, plan_dict):
            captured_validation_inputs.append((source_text, plan_dict))
            return True, []

        fake_llm_response = MagicMock()
        fake_llm_response.tool_calls = []
        fake_llm_response.usage_metadata = None
        fake_llm_response.response_metadata = None
        fake_llm_response.content = json.dumps({
            "sop_id": "SOP-LLM-IGNORED",
            "title": "Demo Procedure",
            "category": "system",
            "platform": "system",
            "is_executable": True,
            "steps": [
                {
                    "step_number": 1,
                    "step_type": "command",
                    "sop_step_description": "Run test command",
                    "command": "echo ok",
                    "source_quote": "Click Button 1",
                }
            ],
        })
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = fake_llm_response
        fake_llm.bind_tools.return_value = fake_llm

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(ep, "CONVERTER_INPUT_LOGS_DIR", os.path.join(tmpdir, "converter_input")), \
             patch.object(ep, "extract_ordered_sop_content", return_value=("ordered_docx_walk", segments)), \
             patch.object(ep, "analyze_and_save_image", side_effect=fake_analyze), \
             patch.object(ep, "run_triage_router", return_value={"classification": "command", "is_executable": True, "detected_platforms": []}), \
             patch.object(ep, "get_llm", return_value=fake_llm), \
             patch.object(ep, "validate_plan_faithfulness_and_linkage", side_effect=fake_validate), \
             patch.object(ep, "log_execution_plan"), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call"), \
             patch.dict(os.environ, {"ELONE_ENABLE_TRIAGE": "1"}):
            draft = ep.plan_okf_from_raw(
                os.path.join(tmpdir, "sample.docx"),
                override_sop_id="SOP-CANON-99",
                pre_extracted_text="Line one prose\nLine two prose\n\nLine three prose",
            )

        self.assertEqual(draft["sop_id"], "SOP-CANON-99")
        self.assertEqual(draft["frontmatter"]["sop_id"], "SOP-CANON-99")
        self.assertEqual([r["anchor_line"] for r in draft["vlm_reports"]], [2, 3])
        self.assertEqual(draft["vlm_reports"][0]["report_path"], "rep_1.md")
        self.assertNotIn("Visual Inspection Report", draft["raw_text"])
        self.assertIn("Visual Inspection Report", draft["enriched_text"])
        self.assertTrue(captured_validation_inputs)
        self.assertIn("Visual Inspection Report", captured_validation_inputs[0][0])

        # Also check override_sop_id on triage unactionable early exit
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(ep, "CONVERTER_INPUT_LOGS_DIR", os.path.join(tmpdir, "converter_input")), \
             patch.object(ep, "extract_ordered_sop_content", return_value=("ordered_docx_walk", segments[:1])), \
             patch.object(ep, "run_triage_router", return_value={"classification": "unactionable", "is_executable": False, "unexecutable_reason": "Policy only"}), \
             patch.dict(os.environ, {"ELONE_ENABLE_TRIAGE": "1"}):
            early = ep.plan_okf_from_raw(
                os.path.join(tmpdir, "sample.docx"),
                override_sop_id="SOP-EARLY-77",
                pre_extracted_text="Line one prose\nLine two prose",
            )
        self.assertEqual(early["sop_id"], "SOP-EARLY-77")
        self.assertEqual(early["frontmatter"]["sop_id"], "SOP-EARLY-77")
        self.assertFalse(early["is_executable"])

    def test_run_a4_verification_uses_real_quotes_vlm_and_gate3(self):
        from schemas.protocol_msg import TaskMessage, Artifact
        from orchestrator.bus import AgentBus
        import orchestrator.agent_runners as runners

        bus = AgentBus()
        cleaned_text = "Open VPN portal\nConnect using office profile"
        vlm_reports = [
            {
                "image_index": 1,
                "label": "Image 1",
                "confidence_score": 0.94,
                "confidence_level": "High",
                "anchor_line": 2,
                "report_text": "SCREEN / CONTEXT: Save Modal\nUI ACTION: Click Save button to store VPN config\nCONFIDENCE SCORE: 0.94",
            }
        ]
        enriched_text = cleaned_text + "\n\n### Visual Inspection Report (Image 1) [HIGH CONFIDENCE: 0.94]:\nClick Save button to store VPN config"

        cleaned_art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="cleaned",
            created_by="A2",
            data={"cleaned_text": cleaned_text, "vlm_reports": vlm_reports, "enriched_text": enriched_text},
        )
        canon_art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="canonical_draft",
            created_by="A2",
            data={
                "sop_id": "SOP-A4-TEST",
                "vlm_reports": vlm_reports,
                "enriched_text": enriched_text,
                "okf_draft": {
                    "sop_id": "SOP-A4-TEST",
                    "steps": [{"step_number": 1, "step_type": "command", "command": "vpn-save"}],
                },
                "canonical_json": {
                    "sop_id": "SOP-A4-TEST",
                    "title": "VPN Save",
                    "steps": [
                        {
                            "n": 1,
                            "action": "Save VPN config",
                            "source_lines": [1, 2],
                            "quote": "Click Save button to store VPN config",
                        }
                    ],
                },
            },
        )
        bus.artifact_store.put(cleaned_art)
        bus.artifact_store.put(canon_art)

        seen_texts = []

        def fake_val(txt, fm):
            seen_texts.append(txt)
            return True, []

        task = TaskMessage(
            sender="orchestrator",
            recipient="A4",
            task_type="verify",
            tenant_id="tn_northwind",
            correlation_id="job-a4-1",
            sop_id="SOP-A4-TEST",
            source_version_id="SOP-A4-TEST@v1",
            source_content_hash="a" * 64,
            idempotency_key="job-a4-1:verify:v1:1:0",
            input_artifact_references=[cleaned_art.artifact_id, canon_art.artifact_id],
        )
        with patch.object(runners, "validate_plan_faithfulness_and_linkage", side_effect=fake_val):
            res_ok = runners.run_a4_verification(task, bus)

        self.assertEqual(res_ok.status, "success")
        self.assertEqual(res_ok.structured_findings["total_quotes"], 1)
        self.assertEqual(res_ok.structured_findings["verified_quotes"], 1)
        self.assertEqual(res_ok.structured_findings["traceability"], 100.0)
        self.assertIn("Visual Inspection Report", seen_texts[0])

        # Case B: Unverified quote MUST trigger Gate 3 needs_review even when Layer 2 returns faithful
        canon_art.data["canonical_json"]["steps"][0]["quote"] = "Completely fabricated step quote nowhere in source"
        task_fail = TaskMessage(
            sender="orchestrator",
            recipient="A4",
            task_type="verify",
            tenant_id="tn_northwind",
            correlation_id="job-a4-2",
            sop_id="SOP-A4-TEST",
            source_version_id="SOP-A4-TEST@v1",
            source_content_hash="a" * 64,
            idempotency_key="job-a4-2:verify:v1:1:0",
            input_artifact_references=[cleaned_art.artifact_id, canon_art.artifact_id],
        )
        with patch.object(runners, "validate_plan_faithfulness_and_linkage", return_value=(True, [])):
            res_fail = runners.run_a4_verification(task_fail, bus)

        self.assertEqual(res_fail.status, "needs_review")
        self.assertEqual(res_fail.structured_findings["verified_quotes"], 0)
        self.assertEqual(res_fail.structured_findings["traceability"], 0.0)
        self.assertTrue(any("Gate 3 Traceability Failure" in i["error"] for i in res_fail.unresolved_issues))

    def test_run_a6_hub_writes_canonical_json_in_committed_category(self):
        from schemas.protocol_msg import TaskMessage, Artifact
        from orchestrator.bus import AgentBus
        from agents.a6_hub.retrieval_catalog import DownstreamRetrievalIndex
        import orchestrator.agent_runners as runners
        import agents.a5_review.draft_store as draft_store
        import agents.a2_structuring.okf_builder as okf_builder
        import agents.a2_structuring.canonical_builder as canonical_builder

        bus = AgentBus()
        raw_text = "Restart spooler service\nnet stop spooler"
        draft_dict = {
            "sop_id": "SOP-A6-CAT",
            "raw_text": raw_text,
            "vlm_reports": [],
            "frontmatter": {
                "sop_id": "SOP-A6-CAT",
                "title": "Restart Print Spooler",
                "category": "networking",
                "platform": "system",
                "description": "Restart spooler.",
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "command",
                        "sop_step_description": "Stop spooler service",
                        "command": "net stop spooler",
                        "source_quote": "Restart spooler service",
                    }
                ],
            },
        }
        canon_dict = canonical_builder.build_canonical_sop_from_draft(draft_dict, raw_text=raw_text)
        canon_art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="canonical_draft",
            created_by="A2",
            data={"okf_draft": draft_dict, "canonical_json": canon_dict},
        )
        sec_art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="security_findings",
            created_by="A3",
            data={"total_secrets_detected": 0, "is_quarantined": False},
        )
        qr_art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="quality_report",
            created_by="A4",
            data={"completeness": 100.0, "traceability": 100.0, "is_faithful": True, "blocking_issues_count": 0},
        )
        dec_art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="review_decision",
            created_by="A5",
            data={"decision": "approve", "reviewer": "lead@corp.com"},
        )
        for a in (canon_art, sec_art, qr_art, dec_art):
            bus.artifact_store.put(a)

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.dict(os.environ, {"ELONE_ALLOW_INSECURE_DEV_KEY": "1"}):
            drafts_dir = os.path.join(tmpdir, "_uploads", "_drafts")
            sops_dir = os.path.join(tmpdir, "sops")
            patterns_dir = os.path.join(tmpdir, "patterns")
            logs_dir = os.path.join(tmpdir, "logs")
            index_path = os.path.join(sops_dir, "index.md")
            os.makedirs(drafts_dir, exist_ok=True)
            os.makedirs(sops_dir, exist_ok=True)

            idx = DownstreamRetrievalIndex(catalog_path=os.path.join(tmpdir, "_catalog.json"))
            with patch.object(draft_store, "DRAFTS_DIR", drafts_dir), \
                 patch.multiple(okf_builder, SOPS_DIR=sops_dir, PATTERNS_DIR=patterns_dir, LOGS_DIR=logs_dir, INDEX_PATH=index_path), \
                 patch.object(canonical_builder, "SOPS_DIR", sops_dir), \
                 patch.object(runners, "_global_retrieval_index", idx):
                draft_store.stage_unapproved_draft("SOP-A6-CAT", draft_dict, canon_dict, "spooler.txt")
                task = TaskMessage(
                    sender="orchestrator",
                    recipient="A6",
                    task_type="publish",
                    tenant_id="tn_northwind",
                    correlation_id="job-a6-1",
                    sop_id="SOP-A6-CAT",
                    source_version_id="SOP-A6-CAT@v1",
                    source_content_hash="b" * 64,
                    idempotency_key="job-a6-1:publish:v1:1:0",
                    input_artifact_references=[canon_art.artifact_id, dec_art.artifact_id],
                )
                res = runners.run_a6_hub(task, bus)

                self.assertEqual(res.status, "success")
                okf_path = res.structured_findings["published_okf_path"]
                canon_path = res.structured_findings["canonical_json_path"]
                self.assertEqual(os.path.dirname(okf_path), os.path.dirname(canon_path))
                self.assertEqual(os.path.basename(os.path.dirname(canon_path)), "networking")
                self.assertIsNone(draft_store.load_staged_draft("SOP-A6-CAT"))
                with open(canon_path, "r", encoding="utf-8") as cf:
                    saved = json.load(cf)
                self.assertEqual(saved["lifecycle"]["state"], "published")


# ---------------------------------------------------------------------------
# 5. OrchestratorLedger Deduplication & Supersede Semantics
# ---------------------------------------------------------------------------

class TestLedgerSupersede(unittest.TestCase):
    def test_default_duplicate_protection_and_nonblocking_states(self):
        from orchestrator.ledger import (
            OrchestratorLedger,
            STATE_DUPLICATE,
            STATE_RECEIVED,
            STATE_AWAITING_REVIEW,
            STATE_APPROVED,
            STATE_PUBLISHED,
            STATE_REJECTED,
            STATE_FAILED,
            STATE_QUARANTINED,
            STATE_SOFT_DELETED,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = OrchestratorLedger(os.path.join(tmpdir, "ledger.json"))
            sha = "1" * 64

            # Blocking state: awaiting_review (default allow_supersede=False)
            j1 = ledger.start_job("job_1", "SOP-1", "tn_a", sha, "u@corp.com")
            self.assertEqual(j1.current_state, STATE_RECEIVED)
            ledger.transition_state("job_1", "extracting")
            ledger.transition_state("job_1", "scanning")
            ledger.transition_state("job_1", "structuring")
            ledger.transition_state("job_1", "assessing")
            ledger.create_review_task("job_1", 10, "L0")
            self.assertEqual(ledger.get_job("job_1").current_state, STATE_AWAITING_REVIEW)

            j_dup = ledger.start_job("job_dup", "SOP-1", "tn_a", sha, "u@corp.com")
            self.assertEqual(j_dup.current_state, STATE_DUPLICATE)

            # Reject j1 -> next start_job succeeds cleanly without allow_supersede
            ledger.record_review_decision("job_1", "reject", reviewer="r@corp.com", actor_type="human", notes="Bad steps")
            self.assertEqual(ledger.get_job("job_1").current_state, STATE_REJECTED)
            j2 = ledger.start_job("job_2", "SOP-1", "tn_a", sha, "u@corp.com")
            self.assertEqual(j2.current_state, STATE_RECEIVED)

            # Fail j2 -> retry j3 succeeds cleanly
            ledger.transition_state("job_2", STATE_FAILED, reason="LLM error")
            j3 = ledger.start_job("job_3", "SOP-1", "tn_a", sha, "u@corp.com")
            self.assertEqual(j3.current_state, STATE_RECEIVED)

            # Quarantine j3 -> retry j4 succeeds cleanly
            ledger.transition_state("job_3", "extracting")
            ledger.transition_state("job_3", "scanning")
            ledger.trigger_quarantine("job_3", 1, ["passwords"])
            self.assertEqual(ledger.get_job("job_3").current_state, STATE_QUARANTINED)
            j4 = ledger.start_job("job_4", "SOP-1", "tn_a", sha, "u@corp.com")
            self.assertEqual(j4.current_state, STATE_RECEIVED)

            # Publish j4 -> Soft-deleted published job -> retry succeeds
            from schemas.governance_models import PublicationGateResult
            gates = PublicationGateResult(passed=True, gates={}, failure_reasons=[])
            ledger.transition_state("job_4", "extracting")
            ledger.transition_state("job_4", "scanning")
            ledger.transition_state("job_4", "structuring")
            ledger.transition_state("job_4", "assessing")
            ledger.create_review_task("job_4", 10, "L0")
            ledger.record_review_decision("job_4", "approve", reviewer="r@corp.com", actor_type="human", publication_gate_check=gates)
            ledger.publish_approved_sop("job_4", sha, 1, gates)
            ledger.soft_delete_sop("job_4", actor="owner@corp.com", role="owner")
            self.assertEqual(ledger.get_job("job_4").current_state, STATE_SOFT_DELETED)
            j5 = ledger.start_job("job_5", "SOP-1", "tn_a", sha, "u@corp.com")
            self.assertEqual(j5.current_state, STATE_RECEIVED)

    def test_allow_supersede_transitions_unpublished_and_blocks_published(self):
        from orchestrator.ledger import (
            OrchestratorLedger,
            STATE_DUPLICATE,
            STATE_RECEIVED,
            STATE_REJECTED,
            STATE_PUBLISHED,
        )
        from schemas.governance_models import PublicationGateResult

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = OrchestratorLedger(os.path.join(tmpdir, "ledger.json"))
            sha_a = "a" * 64
            ledger.start_job("job_a1", "SOP-A", "tn_a", sha_a, "u@corp.com")
            ledger.transition_state("job_a1", "extracting")
            ledger.transition_state("job_a1", "scanning")
            ledger.transition_state("job_a1", "structuring")
            ledger.transition_state("job_a1", "assessing")
            ledger.create_review_task("job_a1", 10, "L0")
            gates = PublicationGateResult(passed=True, gates={}, failure_reasons=[])
            ledger.record_review_decision("job_a1", "approve", reviewer="rev@corp.com", actor_type="human", publication_gate_check=gates)

            # Supersede approved job legally
            j_new = ledger.start_job("job_a2", "SOP-A", "tn_a", sha_a, "u@corp.com", allow_supersede=True)
            self.assertEqual(j_new.current_state, STATE_RECEIVED)
            old_job = ledger.get_job("job_a1")
            self.assertEqual(old_job.current_state, STATE_REJECTED)
            self.assertEqual(old_job.review_task["status"], "superseded")

            # Published job stays protected even with allow_supersede=True
            ledger.transition_state("job_a2", "extracting")
            ledger.transition_state("job_a2", "scanning")
            ledger.transition_state("job_a2", "structuring")
            ledger.transition_state("job_a2", "assessing")
            ledger.create_review_task("job_a2", 10, "L0")
            ledger.record_review_decision("job_a2", "approve", reviewer="rev@corp.com", actor_type="human", publication_gate_check=gates)
            ledger.publish_approved_sop("job_a2", sha_a, 1, gates)
            self.assertEqual(ledger.get_job("job_a2").current_state, STATE_PUBLISHED)

            j_blocked = ledger.start_job("job_a3", "SOP-A", "tn_a", sha_a, "u@corp.com", allow_supersede=True)
            self.assertEqual(j_blocked.current_state, STATE_DUPLICATE)


# ---------------------------------------------------------------------------
# 6. End-to-End FastAPI Re-Ingestion & Governance Lifecycle (Subprocess-Isolated)
# ---------------------------------------------------------------------------

_SUBPROCESS_FASTAPI_DRIVER = r'''
import os
import sys
import json
import glob
import hashlib
from unittest.mock import patch
from starlette.testclient import TestClient

kb_dir = os.environ["ELONE_KB_DIR"]
backend_dir = os.environ["ELONE_BACKEND_DIR"]
sys.path.insert(0, backend_dir)

import server
import api.context as ctx
import api.routes_ingestion as routes_ingestion

client = TestClient(server.app)

def write_upload(name, text):
    p = os.path.join(ctx.UPLOADS_DIR, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p

sop_text = (
    "Purpose: Configure AirRetailer VPN\n"
    "1. Open https://securevpn.airretailer.com in browser\n"
    "2. Launch Remote Desktop Connection from Start menu\n"
    "3. Save office PC connection profile\n"
)
doc_path = write_upload("airvpn_test.txt", sop_text)

mode = {"value": "vlm_ok"}

def fake_plan(filepath, override_sop_id=None, feedback_override=None, pre_extracted_text=None):
    sid = override_sop_id or "SOP-FAKE"
    if mode["value"] == "unactionable":
        return {
            "sop_id": sid,
            "is_executable": False,
            "unexecutable_reason": "Manual web UI workflow only.",
            "raw_text": pre_extracted_text or "",
            "vlm_reports": [],
            "frontmatter": {
                "sop_id": sid,
                "title": "Unactionable Doc",
                "is_executable": False,
                "unexecutable_reason": "Manual web UI workflow only.",
                "steps": [],
            },
        }
    if mode["value"] == "boom":
        raise RuntimeError("Simulated LLM outage")
    vlm_reps = [
        {
            "image_index": 12,
            "label": "Image 12",
            "image_path": "knowledge_base/img_12.png",
            "report_path": "knowledge_base/rep_12.md",
            "confidence_score": 0.95,
            "confidence_level": "High",
            "anchor_line": 4,
            "report_text": (
                "SCREEN / CONTEXT: Office PC Settings\n"
                "UI ACTION: Click the 'Save' button to confirm PC configuration changes\n"
                "CONFIDENCE SCORE: 0.95\n"
            ),
        }
    ]
    return {
        "sop_id": sid,
        "is_executable": True,
        "confidence_score": 0.96,
        "confidence_level": "High",
        "raw_text": pre_extracted_text or sop_text,
        "vlm_reports": vlm_reps,
        "enriched_text": (pre_extracted_text or sop_text) + "\n### Visual Inspection Report (Image 12)\nClick the 'Save' button",
        "frontmatter": {
            "sop_id": sid,
            "title": "AirRetailer VPN & RDP Setup",
            "category": "network",
            "platform": "system",
            "description": "Configure AirRetailer VPN and Remote Desktop.",
            "is_executable": True,
            "steps": [
                {
                    "step_number": 1,
                    "step_type": "command",
                    "sop_step_description": "Open AirRetailer VPN portal in browser",
                    "command": "start https://securevpn.airretailer.com",
                    "source_quote": "Open https://securevpn.airretailer.com in browser",
                },
                {
                    "step_number": 2,
                    "step_type": "command",
                    "sop_step_description": "Save office PC connection profile",
                    "command": "save-pc-profile",
                    "source_quote": "Click the 'Save' button to confirm PC configuration changes",
                },
            ],
        },
    }

def get_upload_item(name):
    res = client.get("/api/uploads")
    assert res.status_code == 200, res.text
    for item in res.json()["files"]:
        if item["filename"] == name:
            return item
    raise AssertionError(f"Upload '{name}' not found in /api/uploads")

with patch.object(routes_ingestion.jit_converter, "plan_okf_from_raw", side_effect=fake_plan):
    # --- A: Ingest -> awaiting_review + legacy manifest repair ---
    r1 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt"})
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1["status"] == "awaiting_review"
    sop_id = d1["sop_id"]
    job_1 = d1["job_id"]
    task_1 = d1["task_id"]
    assert d1["canonical_draft"]["steps"][1]["evidence_source"] == "visual_inspection"
    assert d1["canonical_draft"]["steps"][1]["image_ref"] == "Image 12"
    assert len(d1["canonical_draft"]["media"]) == 1

    # Simulate legacy bug where _processed_manifest had status='success' while playbook wasn't published
    m = ctx.read_manifest()
    m["airvpn_test.txt"]["status"] = "success"
    with open(ctx.MANIFEST_PATH, "w", encoding="utf-8") as mf:
        json.dump(m, mf)

    up_a = get_upload_item("airvpn_test.txt")
    assert up_a["status"] == "awaiting_review", up_a
    assert up_a["playbook_exists"] is False
    assert up_a["reingest_allowed"] is True
    assert up_a["task_id"] == task_1
    assert ctx.read_manifest()["airvpn_test.txt"]["status"] == "awaiting_review"

    # --- B: Duplicate block (reingest=False), then Reject -> Re-ingest creates _r2 ---
    r_dup = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt"})
    assert r_dup.status_code == 409, r_dup.text
    assert r_dup.json()["status"] == "duplicate"

    dec_rej = client.post(
        f"/api/governance/review-tasks/{task_1}/decision",
        json={"decision": "reject", "reviewer": "sec.rev1@corp.com", "notes": "Missing proxy step"},
    )
    assert dec_rej.status_code == 200, dec_rej.text
    up_rej = get_upload_item("airvpn_test.txt")
    assert up_rej["status"] == "rejected", up_rej
    assert "Missing proxy step" in (up_rej["reason"] or "")
    assert up_rej["reingest_allowed"] is True

    r2 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True})
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    job_2 = d2["job_id"]
    task_2 = d2["task_id"]
    # r_dup allocated _r2 as a duplicate record, so retry gets _r3
    assert job_2 == f"{job_1}_r3", job_2
    assert d2["sop_id"] == sop_id

    # Prior rejected & duplicate jobs preserved in ledger history
    jobs = client.get("/api/governance/jobs").json()["jobs"]
    by_id = {j["job_id"]: j for j in jobs}
    assert by_id[job_1]["current_state"] == "rejected"
    assert by_id[f"{job_1}_r2"]["current_state"] == "duplicate"
    assert by_id[job_2]["current_state"] == "awaiting_review"

    # --- C: Supersede active awaiting_review with reingest=True -> _r4 ---
    r3 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True})
    assert r3.status_code == 200, r3.text
    d3 = r3.json()
    job_3 = d3["job_id"]
    task_3 = d3["task_id"]
    assert job_3 == f"{job_1}_r4", job_3
    jobs = {j["job_id"]: j for j in client.get("/api/governance/jobs").json()["jobs"]}
    assert jobs[job_2]["current_state"] == "rejected"
    assert jobs[job_2]["review_task"]["status"] == "superseded"

    # --- D: Reviewer step edit preserves vlm_reports, media, and visual_inspection evidence ---
    edit_res = client.put(
        f"/api/governance/drafts/{sop_id}/steps",
        json={
            "actor": "human.editor@corp.com",
            "steps": [
                {
                    "ref": 1,
                    "sop_step_description": "Open AirRetailer VPN portal in browser",
                    "command": "start https://securevpn.airretailer.com",
                    "source_quote": "Open https://securevpn.airretailer.com in browser",
                },
                {
                    "ref": 2,
                    "sop_step_description": "Save office PC connection profile (edited)",
                    "command": "save-pc-profile --confirm",
                    "source_quote": "Click the 'Save' button to confirm PC configuration changes",
                },
            ],
        },
    )
    assert edit_res.status_code == 200, edit_res.text
    edited_canon = edit_res.json()["canonical_draft"]
    assert edited_canon["steps"][1]["evidence_source"] == "visual_inspection"
    assert edited_canon["steps"][1]["image_ref"] == "Image 12"
    assert len(edited_canon["media"]) == 1

    # --- E: Approve (distinct reviewer != uploader & != editor) + Publish -> locked from re-ingest ---
    dec_app = client.post(
        f"/api/governance/review-tasks/{task_3}/decision",
        json={"decision": "approve", "reviewer": "final.reviewer@corp.com", "confirmed_classification": True},
    )
    assert dec_app.status_code == 200, dec_app.text

    pub_res = client.post(f"/api/governance/sops/{sop_id}/publish", json={"actor": "final.reviewer@corp.com"})
    assert pub_res.status_code == 200, pub_res.text
    pub_json = pub_res.json()
    assert pub_json["status"] == "published"
    md_path = pub_json["playbook_path"]
    assert os.path.exists(md_path)
    canon_path = os.path.join(os.path.dirname(md_path), f"{sop_id}.canonical.json")
    assert os.path.exists(canon_path)
    assert not os.path.exists(os.path.join(ctx.DRAFTS_DIR, f"{sop_id}.draft.json"))

    with open(canon_path, "r", encoding="utf-8") as cf:
        saved_canon = json.load(cf)
    assert saved_canon["lifecycle"]["state"] == "published"
    assert saved_canon["source"]["file_sha256"]
    assert len(saved_canon["media"]) == 1
    assert saved_canon["steps"][1]["evidence_source"] == "visual_inspection"

    up_pub = get_upload_item("airvpn_test.txt")
    assert up_pub["status"] == "success", up_pub
    assert up_pub["playbook_exists"] is True
    assert up_pub["reingest_allowed"] is False

    # Both reingest=False and reingest=True must block while live playbook exists on disk
    assert client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": False}).status_code == 409
    assert client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True}).status_code == 409

    # --- F: Delete via API -> resets /api/uploads to pending -> re-ingest succeeds ---
    del_res = client.request("DELETE", f"/api/sops/{sop_id}", json={"actor": "owner@corp.com", "reason": "Retire old draft"})
    assert del_res.status_code == 200, del_res.text
    up_del = get_upload_item("airvpn_test.txt")
    assert up_del["status"] == "pending", up_del
    assert up_del["playbook_exists"] is False
    assert up_del["reingest_allowed"] is True

    r4 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt"})
    assert r4.status_code == 200, r4.text
    d4 = r4.json()
    task_4 = d4["task_id"]
    assert client.post(
        f"/api/governance/review-tasks/{task_4}/decision",
        json={"decision": "approve", "reviewer": "final.reviewer@corp.com", "confirmed_classification": True},
    ).status_code == 200
    pub4 = client.post(f"/api/governance/sops/{sop_id}/publish", json={"actor": "final.reviewer@corp.com"})
    assert pub4.status_code == 200, pub4.text
    md_path_4 = pub4.json()["playbook_path"]

    # --- G: Manual deletion of .md on disk (orphan published) -> failed -> reingest=True rescues ---
    os.remove(md_path_4)
    up_orphan = get_upload_item("airvpn_test.txt")
    assert up_orphan["status"] == "failed", up_orphan
    assert "missing from disk" in (up_orphan["reason"] or "").lower()
    assert up_orphan["reingest_allowed"] is True

    # Next re-ingest exits unactionable -> must also purge stale/orphaned state & record unactionable
    mode["value"] = "unactionable"
    r5 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True})
    assert r5.status_code == 200, r5.text
    assert r5.json()["status"] == "unactionable"
    up_unact = get_upload_item("airvpn_test.txt")
    assert up_unact["status"] == "unactionable", up_unact
    assert up_unact["reingest_allowed"] is True

    # Retry again after unhandled exception -> failed -> retry succeeds
    mode["value"] = "boom"
    r6 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True})
    assert r6.status_code == 500, r6.text
    up_fail = get_upload_item("airvpn_test.txt")
    assert up_fail["status"] == "failed", up_fail
    assert up_fail["reingest_allowed"] is True

    mode["value"] = "vlm_ok"
    r7 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True})
    assert r7.status_code == 200, r7.text
    assert r7.json()["status"] == "awaiting_review"

    # Re-ingesting as unactionable while draft exists must purge stale .draft.json so no ghost awaiting_review remains
    mode["value"] = "unactionable"
    r8 = client.post("/api/uploads/ingest", json={"filename": "airvpn_test.txt", "reingest": True})
    assert r8.status_code == 200, r8.text
    assert not os.path.exists(os.path.join(ctx.DRAFTS_DIR, f"{sop_id}.draft.json"))
    assert get_upload_item("airvpn_test.txt")["status"] == "unactionable"

    # --- H: Secret Quarantine test ---
    write_upload("secret_sop.txt", "Login step\npassword = \"SuperSecretPass123!\"\napi_key = \"sk_live_51abcdef1234567890\"\n")
    r_sec = client.post("/api/uploads/ingest", json={"filename": "secret_sop.txt"})
    assert r_sec.status_code == 403, r_sec.text
    assert r_sec.json()["status"] == "quarantined"
    # H3: quarantine really deletes the secret-bearing upload; it is no longer listed,
    # and the manifest keeps only metadata (no raw content).
    assert not os.path.exists(os.path.join(ctx.UPLOADS_DIR, "secret_sop.txt")), "quarantined upload was not deleted"
    listed = {f["filename"] for f in client.get("/api/uploads").json()["files"]}
    assert "secret_sop.txt" not in listed, listed
    assert ctx.read_manifest()["secret_sop.txt"]["status"] == "quarantined"

    # --- I: File content modification invalidates stale manifest -> resets to pending ---
    write_upload("airvpn_test.txt", sop_text + "\n4. Modified step line on disk\n")
    up_mod = get_upload_item("airvpn_test.txt")
    assert up_mod["status"] == "pending", up_mod
    assert "airvpn_test.txt" not in ctx.read_manifest()

print("ALL_FASTAPI_REINGESTION_LIFECYCLE_ASSERTIONS_PASSED")
'''


class TestFastApiReingestionLifecycle(unittest.TestCase):
    def test_end_to_end_reingestion_and_vlm_api_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            driver_path = os.path.join(tmpdir, "run_api_driver.py")
            with open(driver_path, "w", encoding="utf-8") as f:
                f.write(_SUBPROCESS_FASTAPI_DRIVER)

            env = dict(os.environ)
            env["ELONE_KB_DIR"] = tmpdir
            env["ELONE_BACKEND_DIR"] = BACKEND_DIR
            env["ELONE_ALLOW_INSECURE_DEV_KEY"] = "1"

            proc = subprocess.run(
                [sys.executable, driver_path],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"Isolated FastAPI lifecycle test failed (exit {proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
            )
            self.assertIn("ALL_FASTAPI_REINGESTION_LIFECYCLE_ASSERTIONS_PASSED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
