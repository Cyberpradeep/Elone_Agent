import pytest
from agents.execution.node import execution_agent


def test_communication_step_escalation_handling():
    state = {
        "execution_plan": {
            "steps": [
                {
                    "step_number": 8,
                    "sop_step_description": "Escalate to L2 Network Team if gateway is reachable but external nodes fail",
                    "step_type": "communication",
                    "command": None,
                    "fallback_sop_id": "L2-NET-ESC-001",
                    "output_parse_instruction": "Escalate ticket to L2"
                }
            ]
        },
        "current_step_index": 0,
        "workflow_status": "in_progress",
        "entities": {"hostname": "Prabanjan", "email": "chezhiantech@gmail.com"},
        "audit_log": []
    }

    cmd = execution_agent(state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update["workflow_status"] == "escalated"
    assert cmd.update["next_action"] == "ESCALATE"
    assert "communication/escalation" in cmd.update["orchestrator_reasoning"]


def test_tool_call_execution():
    state = {
        "execution_plan": {
            "steps": [
                {
                    "step_number": 1,
                    "sop_step_description": "Unlock locked user account in L1 Support Platform",
                    "step_type": "tool_call",
                    "provider": "mock",
                    "function_name": "unlock_user_account",
                    "comm_inputs": {"user_id": "{entities.user_id}"}
                }
            ]
        },
        "current_step_index": 0,
        "workflow_status": "in_progress",
        "entities": {"user_id": "usr_99812", "email": "pradeepnaveen930@gmail.com"},
        "audit_log": []
    }

    cmd = execution_agent(state)
    assert cmd.goto == "execution_result_agent"
    assert cmd.update["last_executed_exit_code"] == 0
    assert "unlock_user_account" in cmd.update["last_executed_command"]


def test_precondition_skipping():
    state = {
        "execution_plan": {
            "steps": [
                {
                    "step_number": 1,
                    "sop_step_description": "Conditional Step",
                    "step_type": "command",
                    "command": "echo hello",
                    "execute_if": "variables.ifeo_key_exists == true"
                }
            ]
        },
        "current_step_index": 0,
        "workflow_status": "in_progress",
        "variables": {"ifeo_key_exists": False},
        "audit_log": []
    }

    cmd = execution_agent(state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update["next_action"] == "SUCCESS"
    assert "skipped" in cmd.update["execution_reasoning"].lower()

