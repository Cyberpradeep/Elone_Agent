"""
Unit Tests for Canonical Schema 1.0 & Downstream Clearance Retrieval Index
==========================================================================
Tests Sections 14, 16, 17, and 18 of SOP Governance Hub v1.0:
1. Canonical JSON Schema 1.0 structural validation.
2. Step sequence continuity check (1..N no gaps).
3. Exception-to-step linkage verification.
4. Downstream agent clearance tier filtering (L0-L3).
5. Cross-tenant retrieval isolation.
6. Published-only indexing restriction.
7. Instant index purge upon SOP revocation.
8. Standard citation string formatting.
9. Audit trail logging for downstream agent queries.
10. Catalog persistence and reload.
"""

import os
import sys
import tempfile
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas.canonical_sop_schema import (
    CanonicalSOPModel,
    validate_canonical_sop_dict,
)
from agents.a6_hub.retrieval_catalog import (
    DownstreamRetrievalIndex,
    normalize_clearance,
    format_citation,
    CLEARANCE_RANKS,
)


def _make_sample_sop(
    sop_id: str = "SOP-1042",
    version: int = 1,
    tenant_id: str = "tn_northwind",
    level: str = "L1",
    score: int = 35,
    state: str = "published",
    title: str = "User Password Reset Procedure",
    steps_count: int = 2,
) -> dict:
    steps = []
    for i in range(1, steps_count + 1):
        steps.append({
            "n": i,
            "action": f"Execute security check step {i}",
            "input": "username@domain.com",
            "expected_outcome": "Step verified successfully",
            "actor": "agent",
            "requires_approval": False,
            "risk": "low",
            "source_lines": [i * 2, i * 2 + 1],
            "quote": f"Execute security check step {i} in accordance with policy",
            "verified": True,
        })

    return {
        "schema_version": "1.0",
        "sop_id": sop_id,
        "version": version,
        "tenant_id": tenant_id,
        "title": title,
        "title_lines": [1, 2],
        "metadata_lines": [3, 4],
        "department": {"status": "present", "value": "IT Operations", "source_lines": [3]},
        "owner": {"status": "present", "value": "R. Menon", "source_lines": [4]},
        "version_label": {"status": "present", "value": "v1.0", "source_lines": [4]},
        "review_date": {"status": "present", "value": "2026-10-23", "source_lines": [4]},
        "source": {
            "filename": f"{sop_id.lower()}.txt",
            "sha256": "8b791e6d790ea1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6",
            "size": 4096,
            "detected_type": "text/plain",
            "pages": 1,
            "extracted_lines": 33,
            "ocr": False,
        },
        "purpose": {
            "text": "Provide clear guidelines for resetting enterprise user passwords securely.",
            "source_lines": [5, 6],
            "quote": "Provide clear guidelines for resetting enterprise user passwords securely.",
            "verified": True,
        },
        "scope": {
            "text": "Applies to all internal IT helpdesk staff across global operations.",
            "source_lines": [7, 8],
            "quote": "Applies to all internal IT helpdesk staff across global operations.",
            "verified": True,
        },
        "preconditions": [
            {
                "text": "User identity verified via secondary authentication challenge.",
                "source_lines": [9, 10],
                "quote": "User identity verified via secondary authentication challenge.",
                "verified": True,
            }
        ],
        "roles": [
            {
                "role": "Service desk agent",
                "responsibility": "Validate identity and execute temporary credential issue.",
                "source_lines": [11, 12],
            }
        ],
        "steps": steps,
        "exceptions": [
            {
                "condition": "Caller cannot provide secondary token",
                "action": "Escalate to Security Operations immediately",
                "escalate_to": "SOC Team",
                "related_step": 1,
                "source_lines": [20, 21],
                "quote": "Escalate to Security Operations immediately if token fails",
            }
        ],
        "notes": [],
        "references": [{"kind": "sop", "target": "SOP-1001", "label": "Identity Verification SOP"}],
        "media": [],
        "issues": [],
        "classification": {
            "level": level,
            "score": score,
            "evidence_categories": ["internal_infrastructure"],
            "rule_level": level,
            "ai_suggested_level": level,
            "rationale": "Standard internal procedure with no confidential customer data.",
            "confirmed": True,
            "confirmed_by": "Security reviewer",
        },
        "quality": {
            "completeness": 92.0,
            "traceability": 100.0,
            "schema_valid": True,
            "blocking_issues_count": 0,
            "quality_score": 96.8,
            "status": "Ready",
        },
        "transformations": [],
        "lifecycle": {
            "state": state,
            "uploaded_by": "author@example.com",
            "created_at": "2026-10-23T10:00:00Z",
            "approvals": [
                {
                    "by": "approver@example.com",
                    "at": "2026-10-23T12:00:00Z",
                    "version": version,
                    "content_sha256": "8b791e6d790ea1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6",
                }
            ],
        },
        "provenance": {
            "producing_agent": "A2_structuring",
            "provider": "elverve_ai",
            "generated_at": "2026-10-23T10:05:00Z",
        },
    }


class TestCanonicalSchema(unittest.TestCase):

    def test_01_valid_canonical_sop_passes(self):
        """Valid canonical SOP dictionary passes validation with zero errors."""
        raw = _make_sample_sop()
        valid, errors, model = validate_canonical_sop_dict(raw)
        self.assertTrue(valid)
        self.assertEqual(len(errors), 0)
        self.assertIsNotNone(model)
        self.assertEqual(model.sop_id, "SOP-1042")
        self.assertEqual(len(model.steps), 2)

    def test_02_step_sequence_gaps_rejected(self):
        """Step numbers with gaps (e.g. 1, 3) must be rejected."""
        raw = _make_sample_sop()
        raw["steps"][1]["n"] = 3  # Gap: 1, 3 instead of 1, 2
        valid, errors, model = validate_canonical_sop_dict(raw)
        self.assertFalse(valid)
        self.assertTrue(any("Step numbering violation" in e for e in errors))

    def test_03_invalid_exception_link_rejected(self):
        """Exception linking to non-existent step index must be rejected."""
        raw = _make_sample_sop()
        raw["exceptions"][0]["related_step"] = 99  # Step 99 does not exist
        valid, errors, model = validate_canonical_sop_dict(raw)
        self.assertFalse(valid)
        self.assertTrue(any("Exception linkage error" in e for e in errors))


class TestRetrievalIndex(unittest.TestCase):

    def setUp(self):
        self.index = DownstreamRetrievalIndex()
        # Seed index with SOPs across L0, L1, L2, L3 tiers
        self.sop_l0 = _make_sample_sop(sop_id="SOP-L0", level="L0", score=10, title="Public Support Directory")
        self.sop_l1 = _make_sample_sop(sop_id="SOP-L1", level="L1", score=30, title="Internal Helpdesk Ticket Routing")
        self.sop_l2 = _make_sample_sop(sop_id="SOP-L2", level="L2", score=65, title="Confidential Database Backup Procedure")
        self.sop_l3 = _make_sample_sop(sop_id="SOP-L3", level="L3", score=85, title="Restricted Production Key Rotation")

        self.index.index_published_sop(self.sop_l0)
        self.index.index_published_sop(self.sop_l1)
        self.index.index_published_sop(self.sop_l2)
        self.index.index_published_sop(self.sop_l3)

    def test_04_unpublished_sop_rejected_from_index(self):
        """Only SOPs in state 'published' can be indexed."""
        draft = _make_sample_sop(sop_id="SOP-DRAFT", state="awaiting_review")
        with self.assertRaises(ValueError) as exc:
            self.index.index_published_sop(draft)
        self.assertIn("Only published SOPs can be added", str(exc.exception))

    def test_05_clearance_filtering_l0_agent(self):
        """An L0 agent querying must ONLY receive L0 Public documents."""
        results = self.index.search(
            query="",
            tenant_id="tn_northwind",
            clearance_level="L0",
            agent_id="public_bot_01",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].sop_id, "SOP-L0")
        self.assertEqual(results[0].classification_level, "L0")

    def test_06_clearance_filtering_l1_agent(self):
        """An L1 agent receives L0 and L1 documents, but L2 and L3 are strictly hidden."""
        results = self.index.search(
            query="",
            tenant_id="tn_northwind",
            clearance_level="L1",
            agent_id="helpdesk_bot_01",
        )
        returned_ids = {r.sop_id for r in results}
        self.assertEqual(returned_ids, {"SOP-L0", "SOP-L1"})
        self.assertNotIn("SOP-L2", returned_ids)
        self.assertNotIn("SOP-L3", returned_ids)

    def test_07_clearance_filtering_l2_agent(self):
        """An L2 agent receives L0, L1, and L2 documents, but L3 is strictly hidden."""
        results = self.index.search(
            query="",
            tenant_id="tn_northwind",
            clearance_level="L2",
            agent_id="devops_bot_01",
        )
        returned_ids = {r.sop_id for r in results}
        self.assertEqual(returned_ids, {"SOP-L0", "SOP-L1", "SOP-L2"})
        self.assertNotIn("SOP-L3", returned_ids)

    def test_08_clearance_filtering_l3_agent(self):
        """An L3 agent has full clearance and receives all published documents."""
        results = self.index.search(
            query="",
            tenant_id="tn_northwind",
            clearance_level="L3",
            agent_id="security_bot_01",
        )
        returned_ids = {r.sop_id for r in results}
        self.assertEqual(returned_ids, {"SOP-L0", "SOP-L1", "SOP-L2", "SOP-L3"})

    def test_09_direct_get_by_id_clearance_denial(self):
        """Direct retrieval by ID enforces clearance with clear denial reason."""
        # L1 agent attempting to fetch L3 SOP directly
        entry, err = self.index.get_by_id(
            sop_id="SOP-L3",
            tenant_id="tn_northwind",
            clearance_level="L1",
        )
        self.assertIsNone(entry)
        self.assertIn("Insufficient clearance", err)

        # L3 agent fetching L3 SOP succeeds
        entry, err = self.index.get_by_id(
            sop_id="SOP-L3",
            tenant_id="tn_northwind",
            clearance_level="L3",
        )
        self.assertIsNotNone(entry)
        self.assertIsNone(err)
        self.assertEqual(entry.sop_id, "SOP-L3")

    def test_10_cross_tenant_isolation(self):
        """An agent from tenant_beta cannot discover or fetch SOPs from tn_northwind."""
        results = self.index.search(
            query="",
            tenant_id="tenant_beta",
            clearance_level="L3",
        )
        self.assertEqual(len(results), 0)

        entry, err = self.index.get_by_id(
            sop_id="SOP-L1",
            tenant_id="tenant_beta",
            clearance_level="L3",
        )
        self.assertIsNone(entry)
        self.assertIn("Tenant isolation policy violation", err)

    def test_11_instant_purge_on_deactivation(self):
        """Purging an SOP immediately removes it from downstream search and direct lookup."""
        purged = self.index.purge_sop("SOP-L1")
        self.assertTrue(purged)

        # Lookup now fails
        entry, err = self.index.get_by_id("SOP-L1", "tn_northwind", "L3")
        self.assertIsNone(entry)
        self.assertIn("not found in published catalog", err)

        # Search no longer returns it
        results = self.index.search("", "tn_northwind", "L3")
        self.assertNotIn("SOP-L1", {r.sop_id for r in results})

    def test_12_standard_citation_formatting(self):
        """Citation follows Section 17 format: {sop_id}@v{version}#{content_sha256[:10]}."""
        entry, _ = self.index.get_by_id("SOP-L0", "tn_northwind", "L0")
        self.assertIsNotNone(entry)
        # sha256 is 8b791e6d790ea... -> first 10 is 8b791e6d79
        self.assertEqual(entry.citation, "SOP-L0@v1#8b791e6d79")

    def test_13_audit_trail_logging(self):
        """Downstream queries append audit trail records."""
        self.index.search(
            query="database backup",
            tenant_id="tn_northwind",
            clearance_level="L1",
            agent_id="agent_helpdesk_42",
            agent_persona="service_desk_agent",
        )
        audit = self.index.get_audit_trail(limit=5)
        self.assertGreater(len(audit), 0)
        last = audit[-1]
        self.assertEqual(last["agent_id"], "agent_helpdesk_42")
        self.assertEqual(last["agent_persona"], "service_desk_agent")
        self.assertEqual(last["clearance_level"], "L1")
        self.assertGreater(last["denied_by_clearance_count"], 0)  # L2 and L3 denied

    def test_14_catalog_persistence(self):
        """Catalog serializes to disk and reloads cleanly."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            cat_path = tf.name

        try:
            idx1 = DownstreamRetrievalIndex(catalog_path=cat_path)
            idx1.index_published_sop(self.sop_l0)
            idx1.index_published_sop(self.sop_l2)

            # Reload in new instance
            idx2 = DownstreamRetrievalIndex(catalog_path=cat_path)
            stats = idx2.get_stats("tn_northwind")
            self.assertEqual(stats["total_published"], 2)
            self.assertEqual(stats["by_tier"]["L0"], 1)
            self.assertEqual(stats["by_tier"]["L2"], 1)
        finally:
            if os.path.exists(cat_path):
                os.remove(cat_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

