import os
import io
import json
import hashlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image

from agents.a1_ingestion.vlm_extractor import (
    analyze_and_save_image,
    clear_image_report_cache,
)
from agents.a2_structuring import execution_planner as ep


def _make_valid_png(color=(255, 0, 0)) -> bytes:
    img = Image.new("RGB", (10, 10), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestVlmReportCaching(unittest.TestCase):
    def setUp(self):
        clear_image_report_cache()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.kb_dir = self.tmp_dir.name
        self.patch_env = patch.dict(os.environ, {"ELONE_KB_DIR": self.kb_dir})
        self.patch_env.start()
        # Patch IMAGES_LOG_DIR in vlm_extractor to use the tmpdir
        self.images_dir = os.path.join(self.kb_dir, "logs", "images")
        self.patch_img_dir = patch("agents.a1_ingestion.vlm_extractor.IMAGES_LOG_DIR", self.images_dir)
        self.patch_img_dir.start()

    def tearDown(self):
        self.patch_img_dir.stop()
        self.patch_env.stop()
        self.tmp_dir.cleanup()
        clear_image_report_cache()

    def test_first_call_invokes_vlm_and_caches_to_disk_with_sha256(self):
        valid_png = _make_valid_png(color=(0, 128, 255))
        fake_report = (
            "SCREEN / CONTEXT: VPN Configuration Window\n"
            "UI ACTION: Click the 'Connect' button\n"
            "CONFIDENCE SCORE: 0.95\n"
            "CONFIDENCE LEVEL: High\n"
        )

        with patch("agents.a1_ingestion.vlm_extractor.analyze_image_bytes", return_value=fake_report) as mock_vlm:
            rep, ref = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)

            mock_vlm.assert_called_once()
            self.assertIn("UI ACTION: Click the 'Connect' button", rep)
            self.assertEqual(ref["confidence_score"], 0.95)
            self.assertEqual(ref["confidence_level"], "High")

            # Check disk files
            sop_dir = os.path.join(self.images_dir, "SOP-VPN-TEST")
            saved_meta = os.path.join(sop_dir, "img_1_report.json")
            self.assertTrue(os.path.exists(saved_meta))

            with open(saved_meta, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self.assertEqual(meta["confidence_score"], 0.95)
            self.assertIn("sha256", meta)

    def test_second_call_memory_cache_hit_zero_vlm_api_calls(self):
        valid_png = _make_valid_png(color=(100, 200, 50))
        fake_report = (
            "SCREEN / CONTEXT: Settings Panel\n"
            "UI ACTION: Enter Gateway IP\n"
            "CONFIDENCE SCORE: 0.92\n"
            "CONFIDENCE LEVEL: High\n"
        )

        with patch("agents.a1_ingestion.vlm_extractor.analyze_image_bytes", return_value=fake_report) as mock_vlm:
            rep1, ref1 = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 1)

            # 2nd call: Exact same image in same process -> Memory cache hit
            rep2, ref2 = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 1, "VLM must NOT be called again on cache hit!")
            self.assertEqual(rep1, rep2)
            self.assertEqual(ref1, ref2)

    def test_disk_cache_hit_after_memory_cleared(self):
        valid_png = _make_valid_png(color=(50, 50, 200))
        fake_report = (
            "SCREEN / CONTEXT: Settings Panel\n"
            "UI ACTION: Enter Gateway IP\n"
            "CONFIDENCE SCORE: 0.88\n"
            "CONFIDENCE LEVEL: High\n"
        )

        with patch("agents.a1_ingestion.vlm_extractor.analyze_image_bytes", return_value=fake_report) as mock_vlm:
            # First call populates disk
            rep1, ref1 = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 1)

            # Clear memory cache to simulate a new process or retry step
            clear_image_report_cache()

            # Second call must hit disk cache without calling VLM
            rep2, ref2 = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 1, "VLM must NOT be called when report exists on disk!")
            self.assertEqual(rep1, rep2)
            self.assertEqual(ref1["confidence_score"], 0.88)

    def test_cache_miss_when_image_bytes_modified(self):
        valid_png_1 = _make_valid_png(color=(255, 0, 0))
        valid_png_2 = _make_valid_png(color=(0, 255, 0))  # Different image

        report_1 = "UI ACTION: Click First"
        report_2 = "UI ACTION: Click Second"

        with patch("agents.a1_ingestion.vlm_extractor.analyze_image_bytes", side_effect=[report_1, report_2]) as mock_vlm:
            rep1, _ = analyze_and_save_image(valid_png_1, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 1)
            self.assertIn("First", rep1)

            # Calling with changed image bytes should detect hash mismatch and re-invoke VLM
            rep2, _ = analyze_and_save_image(valid_png_2, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 2, "VLM must be re-invoked when image content changes!")
            self.assertIn("Second", rep2)

    def test_does_not_cache_failed_vlm_analysis(self):
        valid_png = _make_valid_png(color=(128, 128, 128))
        fail_report = "VLM Analysis FAILED (quota/rate-limit exhausted after 3 attempts): 429 Resource Exhausted"
        success_report = "UI ACTION: Enter Username\nCONFIDENCE SCORE: 0.90\nCONFIDENCE LEVEL: High"

        with patch("agents.a1_ingestion.vlm_extractor.analyze_image_bytes", side_effect=[fail_report, success_report]) as mock_vlm:
            # First attempt fails
            rep1, _ = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 1)
            self.assertIn("FAILED", rep1)

            # Clear memory cache
            clear_image_report_cache()

            # Second attempt should NOT use the failed report from disk; it should retry
            rep2, _ = analyze_and_save_image(valid_png, "image/png", "Image 1", "SOP-VPN-TEST", 1)
            self.assertEqual(mock_vlm.call_count, 2, "VLM must retry if the previous attempt failed!")
            self.assertIn("Enter Username", rep2)

    def test_plan_okf_from_raw_caches_vlm_reports_across_retries(self):
        valid_png = _make_valid_png(color=(30, 60, 90))
        segments = [
            {"type": "text", "content": "Step 1: Open the VPN Client\nLaunch AnyConnect."},
            {"type": "image", "bytes": valid_png, "mime_type": "image/png", "label": "VPN Window"},
        ]
        fake_vlm_output = (
            "SCREEN / CONTEXT: AnyConnect Window\n"
            "UI ACTION: Click the 'Connect' button\n"
            "CONFIDENCE SCORE: 0.95\n"
            "CONFIDENCE LEVEL: High\n"
        )

        from schemas.okf_schema import OKFPlaybookModel, OKFStepModel

        playbook_mock = OKFPlaybookModel(
            sop_id="SOP-VPN-RETRY-01",
            title="VPN Setup",
            platform="system",
            category="network",
            is_executable=True,
            steps=[
                OKFStepModel(
                    step_number=1,
                    step_type="command",
                    sop_step_description="Launch AnyConnect",
                    command="start vpn",
                    shell="powershell",
                    source_quote="Launch AnyConnect.",
                )
            ],
        )

        fake_llm = MagicMock()
        fake_llm.with_structured_output.return_value.invoke.return_value = playbook_mock

        with patch("agents.a1_ingestion.vlm_extractor.analyze_image_bytes", return_value=fake_vlm_output) as mock_vlm, \
             patch.object(ep, "run_triage_router", return_value={"classification": "command", "is_executable": True, "detected_platforms": []}), \
             patch.object(ep, "get_llm", return_value=fake_llm), \
             patch.object(ep, "validate_plan_faithfulness_and_linkage", return_value=(True, [])), \
             patch.object(ep, "log_execution_plan"), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call"):

            # Pass 1: Stage 3 first run
            draft1 = ep.plan_okf_from_raw(
                raw_filepath="vpn_test.docx",
                override_sop_id="SOP-VPN-RETRY-01",
                pre_extracted_text="Step 1: Open the VPN Client\nLaunch AnyConnect.",
                pre_extracted_segments=segments,
            )
            self.assertEqual(mock_vlm.call_count, 1)
            self.assertEqual(len(draft1["vlm_reports"]), 1)
            self.assertEqual(draft1["vlm_reports"][0]["confidence_score"], 0.95)

            # Pass 2: Stage 3 correction / retry after A4 rejection
            draft2 = ep.plan_okf_from_raw(
                raw_filepath="vpn_test.docx",
                override_sop_id="SOP-VPN-RETRY-01",
                feedback_override=["Please ensure step 1 specifies powershell"],
                pre_extracted_text="Step 1: Open the VPN Client\nLaunch AnyConnect.",
                pre_extracted_segments=segments,
            )
            # Call count MUST remain 1: Zero extra VLM calls on retry!
            self.assertEqual(mock_vlm.call_count, 1, "VLM must NOT be called again on retry / correction!")
            self.assertEqual(len(draft2["vlm_reports"]), 1)
            self.assertEqual(draft2["vlm_reports"][0]["confidence_score"], 0.95)


if __name__ == "__main__":
    unittest.main()

