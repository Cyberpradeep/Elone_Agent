"""
Unit Tests for Modular 6-Agent Architecture
============================================
Verifies that all 6 agent modules in backend/agents/ are decoupled, import cleanly,
and execute their domain functions correctly.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.a1_ingestion import (
    validate_sop_file,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    extract_ordered_sop_content,
)
from agents.a2_structuring import (
    build_canonical_sop_from_draft,
    write_canonical_sop_json,
    sync_canonical_to_playbook,
)
from agents.a3_security import (
    scan_for_secrets,
    create_quarantine_incident,
    compute_confidentiality_score,
    score_to_tier,
)
from agents.a4_verification import (
    compute_quality_score,
    verify_quote_trace,
    verify_canonical_quotes,
)
from agents.a5_review import (
    create_review_task,
    verify_separation_of_duties,
    validate_human_reviewer,
    stage_unapproved_draft,
    load_staged_draft,
    purge_staged_draft,
)
from agents.a6_hub import (
    evaluate_publication_gates,
    DownstreamRetrievalIndex,
    normalize_clearance,
    format_citation,
)


class TestAgentsModular(unittest.TestCase):
    def test_a1_ingestion_imports_and_constants(self):
        """A1 exports correct file extension constraints and size caps."""
        self.assertIn(".pdf", ALLOWED_EXTENSIONS)
        self.assertIn(".docx", ALLOWED_EXTENSIONS)
        self.assertGreaterEqual(MAX_FILE_SIZE_BYTES, 10 * 1024 * 1024)

    def test_a2_structuring_canonical_builder(self):
        """A2 builds valid canonical schema from draft."""
        draft = {
            "frontmatter": {
                "sop_id": "SOP-MOD-001",
                "title": "Modular Architecture Test",
                "category": "system",
                "description": "Tests modular agent architecture.",
                "steps": [
                    {
                        "step_number": 1,
                        "sop_step_description": "Verify step extraction",
                        "command": "echo 'ok'",
                        "step_type": "command",
                    }
                ],
            }
        }
        res = build_canonical_sop_from_draft(draft)
        self.assertEqual(res["schema_version"], "1.0")
        self.assertEqual(res["sop_id"], "SOP-MOD-001")
        self.assertEqual(len(res["steps"]), 1)

    def test_a3_security_secret_scanner(self):
        """A3 detects secrets and emits INC-xxxxxx tickets."""
        clean_text = "Standard routine procedure with no credentials."
        has_sec, count, types, _ = scan_for_secrets(clean_text)
        self.assertFalse(has_sec)
        self.assertEqual(count, 0)

        incident = create_quarantine_incident("job_test", "SOP-999", "abc123hash", 2, ["passwords"])
        self.assertTrue(incident.incident_id.startswith("INC-"))
        self.assertTrue(incident.purged)

    def test_a4_verification_quality_formula(self):
        """A4 calculates quality score using 0.4C + 0.4T + 20 - 5B."""
        res = compute_quality_score(
            total_non_blank_lines=10,
            mapped_source_lines=10,
            total_quotes=5,
            verified_quotes=5,
            schema_valid=True,
            blocking_issues_count=0,
        )
        self.assertEqual(res["quality_score"], 100.0)
        self.assertEqual(res["status"], "Ready")

    def test_a5_review_sod_and_staging(self):
        """A5 enforces SoD and stages unapproved drafts."""
        valid_sod, err = verify_separation_of_duties("alice@corp.com", "alice@corp.com")
        self.assertFalse(valid_sod)
        self.assertIn("Separation of Duties", err)

        task = create_review_task("SOP-123", "job-123", 1, "sha256", "alice", 70, "L2")
        self.assertEqual(task.assigned_role, "Security reviewer")

        # Test draft staging
        stage_file = stage_unapproved_draft("SOP-STG-001", {"key": "val"}, {"canonical": True}, "raw.txt")
        self.assertTrue(os.path.exists(stage_file))
        loaded = load_staged_draft("SOP-STG-001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["raw_filename"], "raw.txt")
        purged = purge_staged_draft("SOP-STG-001")
        self.assertTrue(purged)
        self.assertFalse(os.path.exists(stage_file))

    def test_a6_hub_publication_and_citation(self):
        """A6 gatekeeper and citation formatting."""
        citation = format_citation("SOP-1042", 1, "8b791e6d790efedcba")
        self.assertEqual(citation, "SOP-1042@v1#8b791e6d79")

        self.assertEqual(normalize_clearance("L2"), "L2")
        self.assertEqual(normalize_clearance("invalid"), "L0")


if __name__ == "__main__":
    unittest.main()
