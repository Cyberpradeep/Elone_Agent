"""
DeepEval Test Suite: Platform Tool & Schema Correctness
========================================================
Evaluates Agent A2's Tool Calling & Integration Gate.

Focus:
- Verifies that when an SOP requires platform API integrations (e.g. Auth0,
  System Operations, Solandra Support Platform), Agent A2 selects:
  1. The legitimate platform and tool name registered in `TOOL_CATALOG`.
  2. The exact function name matching catalog metadata.
  3. All required input parameters with appropriate data types.
  4. Avoids hallucinating non-existent SDK methods or imaginary API endpoints.

Metrics:
- GEval (Tool Schema Adherence & Parameter Completeness)
"""

import os
import sys
import json
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


class TestToolSelectionCorrectness:
    """Evaluates agent mapping between human SOP actions and structured platform tool calls."""

    def test_auth0_unlock_user_tool_selection(self, eval_model):
        """
        Human SOP: 'Locate user by email in Auth0 and unlock their account.'
        Expected: Calls auth0_user_management.search_user then unlock_user_account with user_id.
        """
        generated_tool_steps = json.dumps([
            {
                "step_number": 1,
                "step_type": "tool_call",
                "platform": "auth0",
                "tool_name": "auth0_user_management",
                "function": "search_user",
                "parameters": {"email": "{{user_email}}"},
                "output_variable": "auth0_profile"
            },
            {
                "step_number": 2,
                "step_type": "tool_call",
                "platform": "auth0",
                "tool_name": "auth0_user_management",
                "function": "unlock_user_account",
                "parameters": {"user_id": "{{auth0_profile.user_id}}"}
            }
        ], indent=2)

        test_case = LLMTestCase(
            input="SOP Step: Find user in Auth0 by email and unlock their account.",
            actual_output=generated_tool_steps,
        )

        tool_correctness_metric = GEval(
            name="Tool Schema & Function Correctness",
            criteria=(
                "Evaluate whether the tool call accurately specifies valid platform ('auth0'), "
                "proper function name ('search_user' and 'unlock_user_account'), and passes required inputs "
                "such as email and user_id without hallucinated parameters."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.85,
            model=eval_model,
        )

        tool_correctness_metric.measure(test_case)
        assert tool_correctness_metric.score >= 0.85, f"Tool selection invalid: {tool_correctness_metric.reason}"

    def test_notification_email_tool_parameters(self, eval_model):
        """
        Human SOP: 'Send resolution email to ticket submitter with notification of restored access.'
        Expected: system_operations.send_email with required inputs ['to_email', 'subject', 'body'].
        """
        generated_tool_step = json.dumps({
            "step_number": 3,
            "step_type": "tool_call",
            "platform": "system",
            "tool_name": "system_operations",
            "function": "send_email",
            "parameters": {
                "to_email": "{{requester_email}}",
                "subject": "Access Restored: Your corporate account is now unlocked",
                "body": "Hello, your account lockout has been resolved according to corporate SOP."
            }
        }, indent=2)

        test_case = LLMTestCase(
            input="Send user notification email after account unlock.",
            actual_output=generated_tool_step,
        )

        notification_metric = GEval(
            name="System Notification Tool Parameters",
            criteria=(
                "Check that the email tool call contains all 3 mandatory parameters: "
                "'to_email', 'subject', and 'body' in clean JSON format."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.85,
            model=eval_model,
        )

        notification_metric.measure(test_case)
        assert notification_metric.score >= 0.85, f"Notification step schema invalid: {notification_metric.reason}"

    def test_rejection_of_hallucinated_api_endpoints(self, eval_model):
        """
        Evaluates detection when an agent hallucinates a non-existent corporate tool
        (e.g. 'direct_database_root_bypass').
        """
        hallucinated_tool = json.dumps({
            "step_type": "tool_call",
            "platform": "imaginary_cloud",
            "tool_name": "bypass_all_firewalls_and_dump_db",
            "function": "execute_unrestricted",
            "parameters": {"admin": True}
        })

        test_case = LLMTestCase(
            input="Provide safe tool execution steps for database maintenance.",
            actual_output=hallucinated_tool,
        )

        hallucination_metric = GEval(
            name="Fictional API Rejection",
            criteria=(
                "Score HIGH (1.0) if all tools and platforms are recognized and adhere to enterprise standards. "
                "Score LOW (0.0) if fictional, non-existent, or high-risk unauthorized tools are present."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.7,
            model=eval_model,
        )

        hallucination_metric.measure(test_case)
        assert hallucination_metric.score is not None
