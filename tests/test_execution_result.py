import pytest
from agents.execution_result.node import execution_result_agent
from agents.execution_result.extractor import extract_variables_and_verdict


def test_fast_tool_json_parsing():
    target_step = {
        "step_number": 1,
        "sop_step_description": "Unlock user account",
        "step_type": "tool_call",
        "provider": "mock",
        "function_name": "unlock_user_account"
    }
    stdout_json = '{"status": "success", "unlocked": true, "user_id": "usr_99812"}'

    ext_vars, verdict, reasoning = extract_variables_and_verdict(
        target_step=target_step,
        step_num=0,
        command="[TOOL CALL: mock.unlock_user_account]",
        stdout=stdout_json,
        stderr="",
        exit_code=0,
        hostname="Carnage",
        variables={}
    )

    assert verdict == "SUCCESS"
    assert ext_vars.get("user_id") == "usr_99812"
    assert ext_vars.get("unlocked").lower() == "true"



def test_execution_result_agent_node():
    state = {
        "execution_plan": {
            "steps": [
                {
                    "step_number": 1,
                    "sop_step_description": "Unlock user account",
                    "step_type": "tool_call",
                    "provider": "mock",
                    "function_name": "unlock_user_account"
                }
            ]
        },
        "current_step_index": 0,
        "last_executed_command": "[TOOL CALL: mock.unlock_user_account]",
        "last_executed_stdout": '{"status": "success", "unlocked": true, "user_id": "usr_99812"}',
        "last_executed_stderr": "",
        "last_executed_exit_code": 0,
        "entities": {"email": "pradeepnaveen930@gmail.com"},
        "variables": {}
    }

    cmd = execution_result_agent(state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update["next_action"] == "SUCCESS"
    assert cmd.update["variables"].get("user_id") == "usr_99812"


def test_nested_json_and_instruction_variable_extraction():
    target_step = {
        "step_number": 1,
        "sop_step_description": "Search for user account by email",
        "step_type": "tool_call",
        "provider": "mock_support_platform",
        "function_name": "search_users",
        "output_parse_instruction": "If response.success.users array is not empty, set variables.account_found = 'true' and store response.success.users[0].id in variables.user_id."
    }
    stdout_json = '{"count": 1, "users": [{"id": 14, "email": "jane.smith@testcorp.com", "is_locked": true}]}'

    ext_vars, verdict, reasoning = extract_variables_and_verdict(
        target_step=target_step,
        step_num=0,
        command="[TOOL CALL: mock_support_platform.search_users]",
        stdout=stdout_json,
        stderr="",
        exit_code=0,
        hostname="Carnage",
        variables={}
    )

    assert verdict == "SUCCESS"
    assert ext_vars.get("user_id") == "14"
    assert ext_vars.get("account_found") == "true"

