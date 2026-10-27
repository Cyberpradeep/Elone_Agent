"""
Unit Test Suite for Dynamic Pipeline Configuration
==================================================
Tests dynamic file input size caps (10MB - 50MB), allowed images count (10 - 15),
dynamic LLM model selection, and runtime configuration reloading.
"""

import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    get_settings,
    get_max_file_size_mb,
    get_max_file_size_bytes,
    get_max_images_per_sop,
    get_max_page_count,
    update_settings,
    reload_settings,
)
from agents.a1_ingestion.intake_validator import check_file_size, validate_sop_file


class TestDynamicConfiguration(unittest.TestCase):
    """Verifies that pipeline settings are dynamically configurable and enforced."""

    def setUp(self):
        # Reload fresh settings before each test
        reload_settings()

    def test_default_configuration_values(self):
        """Verify baseline dynamic configuration values."""
        self.assertGreaterEqual(get_max_file_size_mb(), 10.0)
        self.assertLessEqual(get_max_file_size_mb(), 100.0)
        self.assertIn(get_max_images_per_sop(), [5, 10, 15, 20])
        self.assertGreaterEqual(get_max_page_count(), 10)

    def test_file_size_boundary_enforcement(self):
        """Verify that check_file_size respects the dynamic file size setting."""
        current_max_bytes = get_max_file_size_bytes()
        current_max_mb = get_max_file_size_mb()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            # File just under the limit (e.g. 1 KB)
            f.write(b"Valid small file content.")
            small_path = f.name

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            # File over the limit
            f.write(b"A" * int(current_max_bytes + 1024 * 1024))
            oversized_path = f.name

        try:
            valid, err, size_bytes, size_mb = check_file_size(small_path)
            self.assertTrue(valid)
            self.assertIsNone(err)

            invalid, err, size_bytes, size_mb = check_file_size(oversized_path)
            self.assertFalse(invalid)
            self.assertIn(f"exceeds maximum limit of {current_max_mb:.1f} MB", err)
        finally:
            if os.path.exists(small_path):
                os.remove(small_path)
            if os.path.exists(oversized_path):
                os.remove(oversized_path)

    def test_dynamic_settings_update_in_memory(self):
        """Verify updating image count and file size dynamically affects settings."""
        orig_mb = get_max_file_size_mb()
        orig_imgs = get_max_images_per_sop()

        try:
            # Update dynamically to custom limits
            update_settings({
                "file_upload": {"max_file_size_mb": 45.0},
                "images": {"max_images_per_sop": 12},
            })

            self.assertEqual(get_max_file_size_mb(), 45.0)
            self.assertEqual(get_max_file_size_bytes(), 45 * 1024 * 1024)
            self.assertEqual(get_max_images_per_sop(), 12)
        finally:
            # Restore original
            update_settings({
                "file_upload": {"max_file_size_mb": orig_mb},
                "images": {"max_images_per_sop": orig_imgs},
            })

    def test_llm_model_configuration_structure(self):
        """Verify that dynamic LLM settings contain required planning and validation keys."""
        llm_cfg = get_settings().llm_models
        self.assertIn("execution_planning", llm_cfg)
        self.assertIn("planning_validation", llm_cfg)
        self.assertIn("vlm_image_analysis", llm_cfg)

        plan_conf = llm_cfg["execution_planning"]
        self.assertIn("provider", plan_conf)
        self.assertIn("model", plan_conf)


if __name__ == "__main__":
    unittest.main()

