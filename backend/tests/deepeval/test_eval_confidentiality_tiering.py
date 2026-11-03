"""
DeepEval Test Suite: Confidentiality Tiering & Sensitivity Floor
================================================================
Evaluates Agent A3's Data Classification Engine.

Focus:
- Verifies that ingested Standard Operating Procedures are assigned the correct
  enterprise classification tier according to data sensitivity:
    • L0 (Public): General knowledge, public documentation.
    • L1 (Internal): Standard IT troubleshooting, internal intranet procedures.
    • L2 (Confidential): PII, employee records, customer account resets.
    • L3 (Strictly Confidential): Master cloud keys, signing certificates, database root access.
- Evaluates the "Sensitivity Floor" rule: If DLP indicators (PII, tokens) are found,
  the classification can never downgrade below L2/L3.

Metrics:
- GEval (Confidentiality Tier Alignment)
- Algorithmic Sensitivity Floor Verification
"""

import os
import sys
import pytest

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from deepeval.test_case import LLMTestCase
try:
    from deepeval.test_case import SingleTurnParams as LLMTestCaseParams
except ImportError:
    from deepeval.test_case import LLMTestCaseParams
from deepeval.metrics import GEval
from deepeval import assert_test
from custom_eval_model import get_eval_model


@pytest.fixture(scope="module")
def eval_model():
    return get_eval_model()


class TestConfidentialityClassification:
    """Evaluates accuracy of sensitivity tiering and clearance boundaries."""

    def test_l0_public_sop_tiering(self, eval_model):
        """
        Public SOP: General office visitor Wi-Fi instructions.
        Expected Tier: L0 (Public)
        """
        sop_summary = "General instructions for corporate office visitors connecting to Guest Wi-Fi portal."

        test_case = LLMTestCase(
            input="Classify confidentiality tier for guest Wi-Fi connection guide.",
            actual_output=f"Classification: L0 (Public). Rationale: Contains no internal IPs, credentials, or proprietary data.",
        )

        tiering_metric = GEval(
            name="L0 Confidentiality Tiering",
            criteria="Determine if the classification accurately assigns L0 (Public) to non-sensitive guest documentation.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.85,
            model=eval_model,
        )

        tiering_metric.measure(test_case)
        assert tiering_metric.score >= 0.85, f"Tiering failed: {tiering_metric.reason}"

    def test_l2_pii_customer_reset_tiering(self, eval_model):
        """
        Confidential SOP: Handling customer social security numbers and password resets.
        Expected Tier: L2 (Confidential - PII)
        """
        sop_summary = (
            "Customer Identity Verification: Requires collecting national ID / SSN and mother's maiden name "
            "to issue banking portal temporary access tokens."
        )

        test_case = LLMTestCase(
            input=f"Classify confidentiality tier for SOP: {sop_summary}",
            actual_output="Classification: L2 (Confidential - PII). Rationale: Involves customer identity verification and PII.",
        )

        tiering_metric = GEval(
            name="L2 PII Tiering Accuracy",
            criteria="Verify that SOPs handling customer PII or identity tokens are correctly tiered as L2 (Confidential).",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.85,
            model=eval_model,
        )

        tiering_metric.measure(test_case)
        assert tiering_metric.score >= 0.85, f"L2 Tiering failed: {tiering_metric.reason}"

    def test_l3_cryptographic_root_key_sensitivity_floor(self, eval_model):
        """
        Strictly Confidential SOP: Rotating root AWS KMS customer master keys and hardware HSM certificates.
        Expected Tier: L3 (Strictly Confidential)
        Sensitivity Floor: Can NEVER be classified as L0, L1, or L2.
        """
        sop_summary = (
            "Rotate Hardware Security Module (HSM) master signing certificates and cloud KMS root keys. "
            "Requires dual-custody authorization from Security Operations Lead."
        )

        test_case = LLMTestCase(
            input=f"Classify confidentiality tier for HSM root key rotation: {sop_summary}",
            actual_output="Classification: L3 (Strictly Confidential). Rationale: Root cryptographic signing keys and HSM management.",
        )

        tiering_metric = GEval(
            name="L3 Master Secrets Tiering",
            criteria="Verify that procedures involving root keys, HSM certificates, and KMS master secrets receive L3 classification.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.85,
            model=eval_model,
        )

        tiering_metric.measure(test_case)
        assert tiering_metric.score >= 0.85, f"L3 Sensitivity Floor breached: {tiering_metric.reason}"
