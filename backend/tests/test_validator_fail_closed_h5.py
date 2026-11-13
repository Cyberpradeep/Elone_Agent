import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.a4_verification.plan_validator import (
    validate_plan_faithfulness_and_linkage,
    _coerce_bool,
)


class TestValidatorFailClosedH5(unittest.TestCase):
    def setUp(self):
        self.raw_sop = (
            "Standard Procedure for Network Inspection.\n"
            "Step 1: Check network adapter configurations.\n"
            "Step 2: Flush local DNS resolver cache.\n"
            "This procedure must strictly verify local host state."
        )
        self.valid_plan = {
            "sop_id": "SOP-TEST-H5",
            "required_entities": [],
            "source_action_coverage": [
                {
                    "source_action": "Check network adapter configurations",
                    "coverage": "command_covered",
                    "step_number": 1,
                    "reason": "Runs Get-NetAdapter.",
                },
                {
                    "source_action": "Flush local DNS resolver cache",
                    "coverage": "command_covered",
                    "step_number": 2,
                    "reason": "Runs ipconfig /flushdns.",
                },
            ],
            "steps": [
                {
                    "step_number": 1,
                    "step_type": "command",
                    "sop_step_description": "Check network adapter configurations",
                    "command": "Get-NetAdapter",
                    "shell": "powershell",
                },
                {
                    "step_number": 2,
                    "step_type": "command",
                    "sop_step_description": "Flush local DNS resolver cache",
                    "command": "ipconfig /flushdns",
                    "shell": "powershell",
                },
            ],
        }

    def _invoke_with_mock_llm(self, llm_content: str):
        fake_llm = unittest.mock.MagicMock()
        fake_llm.invoke.return_value = SimpleNamespace(
            content=llm_content,
            usage_metadata={"input_tokens": 15, "output_tokens": 15},
        )
        with patch("agents.a4_verification.plan_validator.get_llm", return_value=fake_llm), \
             patch("gemini_monitor.monitor.check_daily_limit"), \
             patch("gemini_monitor.monitor.record_call"):
            return validate_plan_faithfulness_and_linkage(self.raw_sop, self.valid_plan)

    def test_coerce_bool_helper(self):
        self.assertTrue(_coerce_bool(True))
        self.assertFalse(_coerce_bool(False))
        self.assertTrue(_coerce_bool("true"))
        self.assertTrue(_coerce_bool("True"))
        self.assertTrue(_coerce_bool("1"))
        self.assertTrue(_coerce_bool("yes"))
        self.assertFalse(_coerce_bool("false"))
        self.assertFalse(_coerce_bool("False"))
        self.assertFalse(_coerce_bool("0"))
        self.assertFalse(_coerce_bool("no"))
        self.assertIsNone(_coerce_bool("maybe"))
        self.assertIsNone(_coerce_bool(None))
        self.assertIsNone(_coerce_bool([]))
        self.assertIsNone(_coerce_bool({}))

    def test_unparseable_malformed_json_fails_closed(self):
        """Malformed JSON must fail closed (H5 finding)."""
        malformed = "```json\n{\n  'is_faithful': true, INVALID_JSON_SYNTAX\n```"
        is_valid, errors = self._invoke_with_mock_llm(malformed)
        self.assertFalse(is_valid)
        self.assertTrue(any("Layer 2 Security Error" in err for err in errors))
        self.assertTrue(any("could not be parsed as valid JSON" in err for err in errors))

    def test_plain_text_conversational_fails_closed(self):
        """Conversational text with no JSON must fail closed (previously failed open)."""
        conversational = "I reviewed the SOP and the plan looks completely fine and faithful. All commands match."
        is_valid, errors = self._invoke_with_mock_llm(conversational)
        self.assertFalse(is_valid)
        self.assertTrue(any("Layer 2 Security Error" in err for err in errors))
        self.assertTrue(any("could not be parsed as valid JSON" in err for err in errors))

    def test_missing_is_faithful_fails_closed(self):
        """JSON missing 'is_faithful' must not default to True and must fail closed."""
        missing_verdict = json.dumps({
            "confidence_score": 0.9,
            "confidence_level": "High",
            "validation_feedback": "Plan appears correct but verdict field omitted."
        })
        is_valid, errors = self._invoke_with_mock_llm(missing_verdict)
        self.assertFalse(is_valid)
        self.assertTrue(any("missing required 'is_faithful' field" in err for err in errors))

    def test_invalid_is_faithful_type_fails_closed(self):
        """Non-boolean 'is_faithful' must fail closed."""
        invalid_type = json.dumps({
            "is_faithful": "indeterminate",
            "confidence_score": 0.5,
        })
        is_valid, errors = self._invoke_with_mock_llm(invalid_type)
        self.assertFalse(is_valid)
        self.assertTrue(any("must be a valid boolean" in err for err in errors))

    def test_valid_faithful_verdict_passes(self):
        """Valid JSON asserting is_faithful=True must pass."""
        valid_resp = json.dumps({
            "is_faithful": True,
            "injection_detected": False,
            "confidence_score": 0.98,
            "confidence_level": "High",
            "confidence_reason": "All steps verified against SOP.",
            "command_preservation_reasoning": "All commands preserved.",
            "hallucination_check_reasoning": "No extra commands.",
            "fallback_referral_reasoning": "None needed.",
            "injection_reasoning": "None.",
            "dropped_commands": [],
            "hallucinated_commands": [],
            "malicious_steps": [],
            "validation_feedback": "PASSED FAITHFULNESS INSPECTION"
        })
        is_valid, errors = self._invoke_with_mock_llm(valid_resp)
        self.assertTrue(is_valid, f"Expected pass, got errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_explicit_unfaithful_verdict_fails(self):
        """Valid JSON asserting is_faithful=False must fail."""
        unfaithful_resp = json.dumps({
            "is_faithful": False,
            "injection_detected": False,
            "confidence_score": 0.95,
            "confidence_level": "High",
            "dropped_commands": ["Test-Connection 8.8.8.8"],
            "hallucinated_commands": [],
            "validation_feedback": "SOP required Test-Connection which was dropped."
        })
        is_valid, errors = self._invoke_with_mock_llm(unfaithful_resp)
        self.assertFalse(is_valid)
        self.assertTrue(any("Layer 2 Faithfulness Error" in err for err in errors))
        self.assertTrue(any("Test-Connection" in err for err in errors))

    def test_injection_detected_verdict_fails(self):
        """Valid JSON asserting injection_detected=True must fail as security error."""
        injection_resp = json.dumps({
            "is_faithful": True,
            "injection_detected": True,
            "injection_reasoning": "Adversarial prompt injection attempting credential theft.",
            "malicious_steps": [1]
        })
        is_valid, errors = self._invoke_with_mock_llm(injection_resp)
        self.assertFalse(is_valid)
        self.assertTrue(any("Layer 2 Security Error" in err for err in errors))
        self.assertTrue(any("Prompt injection or malicious command payload detected" in err for err in errors))

    def test_string_boolean_coercion_works(self):
        """String booleans 'true' and 'false' are safely coerced without Python truthy bug."""
        false_str_resp = json.dumps({
            "is_faithful": "false",
            "dropped_commands": ["ipconfig /renew"],
            "validation_feedback": "Dropped command ipconfig /renew"
        })
        is_valid, errors = self._invoke_with_mock_llm(false_str_resp)
        self.assertFalse(is_valid)
        self.assertTrue(any("Layer 2 Faithfulness Error" in err for err in errors))

        true_str_resp = json.dumps({
            "is_faithful": "true",
            "injection_detected": "false",
            "confidence_score": 0.9,
            "validation_feedback": "PASSED FAITHFULNESS INSPECTION"
        })
        is_valid, errors = self._invoke_with_mock_llm(true_str_resp)
        self.assertTrue(is_valid, f"Expected pass, got errors: {errors}")

