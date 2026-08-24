import pytest
from elone_sop import validate_plan_faithfulness_and_linkage


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
                "sop_step_description": "Search user account via solandra API with employee_id EMP123",
                "step_type": "tool_call",
                "platform": "solandra",
                "function_name": "search_user",
                "comm_inputs": {
                    "employee_id": "EMP123"
                }
            }
        ]
    }
    is_valid, errors = validate_plan_faithfulness_and_linkage("Search user account via solandra API with employee_id EMP123", valid_tool_plan)
    assert is_valid is True
    assert len(errors) == 0


def test_tool_call_layer1_validation_fail_missing_input():
    invalid_tool_plan = {
        "steps": [
            {
                "step_number": 1,
                "sop_step_description": "Search user account via solandra API",
                "step_type": "tool_call",
                "platform": "solandra",
                "function_name": "search_user",
                "comm_inputs": {}  # Missing required input 'employee_id'
            }
        ]
    }
    is_valid, errors = validate_plan_faithfulness_and_linkage("Search user account via solandra API", invalid_tool_plan)
    assert is_valid is False
    assert any("missing required input parameter 'employee_id'" in err for err in errors)

