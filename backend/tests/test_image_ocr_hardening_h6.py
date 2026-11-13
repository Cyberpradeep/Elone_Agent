import os
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from agents.a2_structuring import execution_planner as ep
from agents.a1_ingestion import document_extractor as de


class TestImageOcrHardeningH6(unittest.TestCase):
    def test_plan_okf_from_raw_processes_pre_extracted_image_segments(self):
        """H6: Image segments passed to the planner are not dropped and trigger VLM inspection."""
        segments = [
            {"type": "text", "content": "Step 1: Check VPN settings\nVerify gateway connection."},
            {
                "type": "image",
                "bytes": b"fakeimagebytes",
                "mime_type": "image/png",
                "label": "Gateway Settings Screen",
            },
            {"type": "text", "content": "Step 2: Restart VPN adapter.\nRestart-Service vpn"},
        ]

        fake_vlm_report = "Visible gateway IP is 10.0.0.1. Status: Disconnected."
        fake_vlm_ref = {
            "file_path": "report_1.md",
            "image_path": "img_1.png",
            "confidence_score": 0.92,
            "confidence_level": "High",
        }

        fake_llm = MagicMock()
        fake_llm.invoke.return_value = SimpleNamespace(
            content=json.dumps({
                "sop_id": "SOP-VPN-001",
                "title": "VPN Gateway Reconnect",
                "platform": "system",
                "category": "network",
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "command",
                        "sop_step_description": "Restart VPN service",
                        "command": "Restart-Service vpn",
                        "shell": "powershell",
                    }
                ],
            }),
            usage_metadata={"input_tokens": 50, "output_tokens": 50},
        )

        with patch.object(ep, "extract_ordered_sop_content") as mock_extract, \
             patch.object(ep, "analyze_and_save_image", return_value=(fake_vlm_report, fake_vlm_ref)) as mock_img_vlm, \
             patch.object(ep, "get_llm", return_value=fake_llm), \
             patch.object(ep, "validate_plan_faithfulness_and_linkage", return_value=(True, [])), \
             patch.object(ep, "log_execution_plan"), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call"):
            
            draft = ep.plan_okf_from_raw(
                raw_filepath="dummy_sop.docx",
                override_sop_id="SOP-VPN-001",
                pre_extracted_text="Step 1: Check VPN settings\nVerify gateway connection.\n\nStep 2: Restart VPN adapter.\nRestart-Service vpn",
                pre_extracted_segments=segments,
            )

        # 1. extract_ordered_sop_content must NOT be re-called because segments were provided directly
        mock_extract.assert_not_called()

        # 2. VLM image analysis must be invoked for the image segment
        mock_img_vlm.assert_called_once()
        self.assertEqual(len(draft.get("vlm_reports", [])), 1)
        self.assertEqual(draft["vlm_reports"][0]["confidence_score"], 0.92)
        self.assertIn("Visual Inspection Report (Gateway Settings Screen)", draft.get("enriched_text", ""))

    def test_vision_ocr_runs_secret_scan_on_ocr_text(self):
        """H6: OCR text is scanned with redact_sensitive_dlp and secrets are masked."""
        class _FakePix:
            def tobytes(self, fmt):
                return b"jpegbytes"

        class _FakePage:
            def get_pixmap(self, dpi=100):
                return _FakePix()

        fake_doc = [_FakePage()]
        fake_llm = MagicMock()
        fake_llm.model = "meta/test-vision"
        fake_llm.invoke.return_value = SimpleNamespace(
            content="Page 1 SOP\nDatabase Password: SuperSecretAdminPassword99!\nConnect to DB",
            usage_metadata={"input_tokens": 10, "output_tokens": 20},
        )

        with patch.object(de, "get_llm", return_value=fake_llm), \
             patch("config.settings.get_max_page_count", return_value=5), \
             patch("config.settings.get_max_images_per_sop", return_value=5), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call"):
            out = de._run_vision_ocr(fake_doc, "scanned_credentials.pdf")

        # Must NOT contain raw secret password
        self.assertNotIn("SuperSecretAdminPassword99!", out)
        self.assertIn("[DLP_REDACTED_PASSWORD]", out)

    def test_vision_ocr_records_call_and_checks_limits(self):
        """H6: OCR calls check daily limits and record token/image usage."""
        class _FakePix:
            def tobytes(self, fmt):
                return b"jpegbytes"

        class _FakePage:
            def get_pixmap(self, dpi=100):
                return _FakePix()

        fake_doc = [_FakePage() for _ in range(3)]
        fake_llm = MagicMock()
        fake_llm.model = "meta/llama-3.2-11b-vision-instruct"
        fake_llm.invoke.return_value = SimpleNamespace(
            content="Transcribed text from page",
            usage_metadata={"input_tokens": 100, "output_tokens": 50},
        )

        with patch.object(de, "get_llm", return_value=fake_llm), \
             patch("config.settings.get_max_page_count", return_value=2), \
             patch("config.settings.get_max_images_per_sop", return_value=10), \
             patch("gemini_monitor.monitor.check_daily_limit") as chk, \
             patch("gemini_monitor.monitor.record_call") as rec:
            out = de._run_vision_ocr(fake_doc, "test.pdf")

        # Capped at page_cap=2
        self.assertEqual(fake_llm.invoke.call_count, 2)
        self.assertEqual(chk.call_count, 2)
        self.assertEqual(rec.call_count, 2)
        rec.assert_called_with(
            caller="vision_ocr",
            model="meta/llama-3.2-11b-vision-instruct",
            provider="nvidia",
            input_tokens=100,
            output_tokens=50,
            image_tokens=1024,
        )

    def test_execution_planner_secret_scans_before_structuring(self):
        """H6: Combined raw text is secret-scanned before LLM structuring prompts."""
        raw_text_with_secret = (
            "Step 1: Authenticate to internal portal.\n"
            "Password: TopSecretValue99!\n"
            "Step 2: Restart-Service spooler"
        )
        segments = [{"type": "text", "content": raw_text_with_secret}]

        captured_system_prompts = []
        fake_llm = MagicMock()
        def _fake_invoke(messages):
            msg = messages[0]
            txt = msg.content if hasattr(msg, "content") else (msg.get("content") if isinstance(msg, dict) else str(msg))
            captured_system_prompts.append(txt)
            payload = {
                "sop_id": "SOP-SECRET-TEST",
                "title": "Secret Test",
                "platform": "system",
                "category": "system",
                "is_executable": True,
                "steps": [
                    {
                        "step_number": 1,
                        "step_type": "command",
                        "sop_step_description": "Restart-Service spooler",
                        "command": "Restart-Service spooler",
                        "shell": "powershell",
                    }
                ],
            }
            return SimpleNamespace(
                content=f"```json\n{json.dumps(payload)}\n```",
                usage_metadata={"input_tokens": 20, "output_tokens": 20},
            )
        fake_llm.invoke.side_effect = _fake_invoke
        fake_llm.bind_tools.return_value = fake_llm

        with patch.object(ep, "run_triage_router", return_value={"classification": "command", "is_executable": True, "detected_platforms": []}), \
             patch.object(ep, "get_llm", return_value=fake_llm), \
             patch.object(ep, "validate_plan_faithfulness_and_linkage", return_value=(True, [])), \
             patch.object(ep, "log_execution_plan"), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call"):
            draft = ep.plan_okf_from_raw(
                raw_filepath="secret_sop.txt",
                override_sop_id="SOP-SECRET-TEST",
                pre_extracted_text=raw_text_with_secret,
                pre_extracted_segments=segments,
            )

        self.assertTrue(captured_system_prompts)
        for prompt in captured_system_prompts:
            self.assertNotIn("TopSecretValue99!", prompt)
            self.assertIn("[DLP_REDACTED_PASSWORD]", prompt)

