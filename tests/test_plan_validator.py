import pytest
from agents.plan_validator.validator import validate_plan_faithfulness_and_linkage


def test_layer1_deterministic_validation():
    valid_plan = {
        "steps": [
            {
                "step_number": 1,
                "sop_step_description": "Run diagnostic check",
                "step_type": "command",
                "command": "ipconfig /all",
                "output_parse_instruction": "Check for IPv4"
            }
        ]
    }
    is_valid, errors = validate_plan_faithfulness_and_linkage("ipconfig /all", valid_plan)
    assert is_valid is True
    assert len(errors) == 0


def test_invalid_empty_steps_validation():
    invalid_plan = {"steps": []}
    is_valid, errors = validate_plan_faithfulness_and_linkage("some text", invalid_plan)
    assert is_valid is False
    assert "contains zero execution steps" in errors[0]


def test_tool_call_layer1_validation_pass():
    valid_tool_plan = {
        "steps": [
            {
                "step_number": 1,
                "sop_step_description": "Unlock user account via admin API",
                "step_type": "tool_call",
                "provider": "mock_support_platform",
                "function_name": "unlock_user_account",
                "comm_inputs": {
                    "user_id": "usr_99812"
                }
            }
        ]
    }
    is_valid, errors = validate_plan_faithfulness_and_linkage("Unlock customer account", valid_tool_plan)
    assert is_valid is True
    assert len(errors) == 0


def test_tool_call_layer1_validation_fail_missing_input():
    invalid_tool_plan = {
        "steps": [
            {
                "step_number": 1,
                "sop_step_description": "Unlock user account via admin API",
                "step_type": "tool_call",
                "provider": "mock_support_platform",
                "function_name": "unlock_user_account",
                "comm_inputs": {}  # Missing required input 'user_id'
            }
        ]
    }
    is_valid, errors = validate_plan_faithfulness_and_linkage("Unlock customer account", invalid_tool_plan)
    assert is_valid is False
    assert any("missing required input parameter 'user_id'" in err for err in errors)

