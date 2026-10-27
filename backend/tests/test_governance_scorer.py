"""
Automated Verification Suite for Governance Scorer (Step 1)
============================================================
Tests Section 11 Confidentiality Scoring, Section 12 Quality Scoring,
and Verbatim Quote Tracing against the Frozen v1.0 Specification.
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

from agents.a3_security.confidentiality_engine import (
    compute_confidentiality_score,
    score_to_tier,
)
from agents.a4_verification.quote_tracer import (
    verify_quote_trace,
    verify_canonical_quotes,
)
from agents.a4_verification.quality_engine import (
    compute_quality_score,
)


class TestConfidentialityScoring(unittest.TestCase):
    def test_01_baseline_internal_sop(self):
        """Minimal clean SOP text has baseline 5 points (L0 Public)."""
        res = compute_confidentiality_score("Simple public document with no sensitive data.")
        self.assertEqual(res["score"], 5)
        self.assertEqual(res["level"], "L0")
        self.assertEqual(res["rule_level"], "L0")
        self.assertFalse(res["conflict"])
        self.assertFalse(res["quarantine_triggered"])
        self.assertFalse(res["requires_security_reviewer"])
        self.assertEqual(res["review_deadline_hours"], 48)

    def test_02_secret_detection_triggers_quarantine(self):
        """Live passwords or keys add +45 and trigger terminal quarantine."""
        res = compute_confidentiality_score(
            text="User password reset procedure",
            dlp_stats={"passwords": 1, "api_keys": 0, "emails": 0, "phones": 0, "private_keys": 0}
        )
        self.assertEqual(res["score"], 50)  # 5 + 45
        self.assertEqual(res["level"], "L1")
        self.assertTrue(res["quarantine_triggered"])
        self.assertIn("credentials_or_secrets", res["evidence_categories"])

    def test_03_internal_infrastructure_capping(self):
        """Internal IPs and hostnames add +10 for first, +5 addl, capped at +25."""
        # 1 infra item: +10 -> total 15
        res1 = compute_confidentiality_score("Connect to 10.0.0.1.")
        self.assertEqual(res1["score"], 15)  # 5 + 10

        # 5 infra items: +10 + 4*5 = +30 -> capped at +25 -> total 30
        res_capped = compute_confidentiality_score(
            "Connect to 10.0.0.1 and 192.168.1.50 or vpn.corp.example or server.internal via HKLM\\Software."
        )
        self.assertEqual(res_capped["score"], 30)  # 5 + 25
        self.assertEqual(res_capped["level"], "L1")

    def test_04_personal_data_pii_capping(self):
        """PII emails and phones add +10 first, +5 addl, capped at +25."""
        res = compute_confidentiality_score(
            text="Contact support.",
            dlp_stats={"emails": 2, "phones": 1}  # 3 PII items: 10 + 2*5 = +20
        )
        self.assertEqual(res["score"], 25)  # 5 + 20
        self.assertEqual(res["level"], "L1")

    def test_05_explicit_label_and_ocr(self):
        """Explicit confidentiality label adds +15; OCR adds +10."""
        res = compute_confidentiality_score(
            text="STRICTLY CONFIDENTIAL corporate policy.",
            is_ocr=True
        )
        self.assertEqual(res["score"], 30)  # 5 + 15 + 10
        self.assertIn("explicit_confidentiality_label", res["evidence_categories"])
        self.assertIn("ocr_source_uncertainty", res["evidence_categories"])

    def test_06_non_negotiable_ai_floor_raising(self):
        """AI suggested level can RAISE sensitivity floor, adjusting score to level floor."""
        res = compute_confidentiality_score(
            text="Baseline internal procedure.",  # Rule score: 5 (L0)
            ai_advisory={"suggested_level": "L2"}  # AI suggests L2 Confidential
        )
        self.assertEqual(res["rule_level"], "L0")
        self.assertEqual(res["level"], "L2")  # Elevated to L2
        self.assertEqual(res["score"], 51)    # Raised to L2 floor (51)
        self.assertTrue(res["conflict"])
        self.assertTrue(res["requires_security_reviewer"])
        self.assertEqual(res["review_deadline_hours"], 24)

    def test_07_non_negotiable_ai_floor_lowering_blocked(self):
        """AI cannot LOWER the sensitivity level; code rule remains authoritative."""
        # Document with label + infra = 5 + 15 + 10 = 30 (L1 Internal)
        res = compute_confidentiality_score(
            text="CONFIDENTIAL: connect to 10.1.2.3",
            ai_advisory={"suggested_level": "L0"}  # AI tries to lower to L0 Public
        )
        self.assertEqual(res["rule_level"], "L1")
        self.assertEqual(res["level"], "L1")  # Kept at L1 (Rule won!)
        self.assertEqual(res["score"], 30)
        self.assertTrue(res["conflict"])  # Disagreement flagged for human reviewer

    def test_08_review_escalation_threshold(self):
        """Scores >= 60 mandate a Security Reviewer sign-off."""
        # 5 base + 15 label + 25 infra + 15 security_controls = 60
        res = compute_confidentiality_score(
            text="CONFIDENTIAL: 10.0.0.1 192.168.1.1 vpn.internal.corp server.lan HKLM\\Key",
            ai_advisory={"security_controls": True}
        )
        self.assertGreaterEqual(res["score"], 60)
        self.assertTrue(res["requires_security_reviewer"])


class TestVerbatimQuoteTracer(unittest.TestCase):
    def setUp(self):
        self.source_lines = [
            "SOP-IT-014 Connect to Corporate VPN (Windows)",
            "Version: 3.0 Owner: IT Service Desk Lead",
            "",
            "1. PURPOSE",
            "Help a user connect a Windows laptop to the Northwind corporate VPN.",
            "",
            "4. PROCEDURE",
            "4.1 Click the GlobalConnect icon in the system tray.",
            "4.2 In the Portal field, enter vpn.northwind.example and click Connect.",
            "4.3 Sign in with directory credentials.",
            "4.4 Approve the sign-in request in Authenticator within 60 seconds."
        ]

    def test_09_exact_quote_match(self):
        """Exact verbatim quote within cited line range passes verification."""
        is_ok, context = verify_quote_trace(
            raw_lines=self.source_lines,
            start_line=8,
            end_line=8,
            quote="Click the GlobalConnect icon in the system tray."
        )
        self.assertTrue(is_ok)

    def test_10_pm1_line_boundary_match(self):
        """Verbatim quote located +/-1 line away from citation still verifies cleanly."""
        # Cited at line 9, but actual quote is at line 8 (within -1 line margin)
        is_ok, context = verify_quote_trace(
            raw_lines=self.source_lines,
            start_line=9,
            end_line=9,
            quote="Click the GlobalConnect icon in the system tray."
        )
        self.assertTrue(is_ok)

    def test_11_hallucinated_quote_fails(self):
        """Fabricated instruction not present in window fails verification."""
        is_ok, context = verify_quote_trace(
            raw_lines=self.source_lines,
            start_line=8,
            end_line=8,
            quote="Reboot your computer into safe mode and format drive C."
        )
        self.assertFalse(is_ok)

    def test_12_batch_canonical_quote_verification(self):
        """Batch verifies steps and preconditions, updating verified flags."""
        steps = [
            {"action": "Click icon", "source_lines": [8, 8], "quote": "Click the GlobalConnect icon"},
            {"action": "Enter portal", "source_lines": [9, 9], "quote": "enter vpn.northwind.example"},
            {"action": "Fake step", "source_lines": [4, 4], "quote": "Launch rocket to the moon"}
        ]
        total, verified, unverified = verify_canonical_quotes(steps, self.source_lines)
        self.assertEqual(total, 3)
        self.assertEqual(verified, 2)
        self.assertEqual(len(unverified), 1)
        self.assertEqual(unverified[0]["action"], "Fake step")


class TestQualityScoring(unittest.TestCase):
    def test_13_perfect_score_ready_status(self):
        """100% completeness, 100% traceability, valid schema, 0 issues -> Score 100, Ready."""
        res = compute_quality_score(
            total_non_blank_lines=50,
            mapped_source_lines=50,
            total_quotes=10,
            verified_quotes=10,
            schema_valid=True,
            blocking_issues_count=0
        )
        # 0.4*100 + 0.4*100 + 20 - 0 = 100.0
        self.assertEqual(res["quality_score"], 100.0)
        self.assertEqual(res["status"], "Ready")
        self.assertTrue(res["is_ready"])

    def test_14_needs_attention_status(self):
        """Valid schema with traceability >= 50% but blocking issues -> Needs attention."""
        res = compute_quality_score(
            total_non_blank_lines=40,
            mapped_source_lines=36,  # 90.0%
            total_quotes=10,
            verified_quotes=8,       # 80.0%
            schema_valid=True,
            blocking_issues_count=2   # Penalty: 10
        )
        # 0.4*90 + 0.4*80 + 20 - 10 = 36 + 32 + 20 - 10 = 78.0
        self.assertEqual(res["quality_score"], 78.0)
        self.assertEqual(res["status"], "Needs attention")
        self.assertFalse(res["is_ready"])

    def test_15_failed_checks_low_traceability(self):
        """Traceability < 50% results in Failed checks."""
        res = compute_quality_score(
            total_non_blank_lines=30,
            mapped_source_lines=30,
            total_quotes=10,
            verified_quotes=4,       # 40% < 50%
            schema_valid=True,
            blocking_issues_count=0
        )
        self.assertEqual(res["status"], "Failed checks")
        self.assertFalse(res["is_ready"])

    def test_16_failed_checks_invalid_schema(self):
        """Invalid schema results in Failed checks and loses 20 points."""
        res = compute_quality_score(
            total_non_blank_lines=20,
            mapped_source_lines=20,
            total_quotes=5,
            verified_quotes=5,
            schema_valid=False,     # Invalid!
            blocking_issues_count=0
        )
        # 0.4*100 + 0.4*100 + 0 - 0 = 80.0
        self.assertEqual(res["quality_score"], 80.0)
        self.assertEqual(res["status"], "Failed checks")

    def test_17_quarantine_overrides_quality(self):
        """Security quarantine overrides every other quality score."""
        res = compute_quality_score(
            total_non_blank_lines=50,
            mapped_source_lines=50,
            total_quotes=10,
            verified_quotes=10,
            schema_valid=True,
            blocking_issues_count=0,
            is_quarantined=True
        )
        self.assertEqual(res["status"], "Quarantined")
        self.assertFalse(res["is_ready"])


if __name__ == "__main__":
    unittest.main()

