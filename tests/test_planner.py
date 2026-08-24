import pytest
from agents.planner.binder import validate_planner_execution_plan


def test_deterministic_planner_binder_validation():
    valid_plan = {
        "steps": [
            {
                "step_number": 1,
                "sop_step_description": "Verify IP configuration",
                "step_type": "command",
                "command": "ipconfig /all",
                "expected_output_contains": "IPv4 Address"
            }
        ]
    }
    is_valid, errors = validate_planner_execution_plan(valid_plan)
    assert is_valid is True
    assert len(errors) == 0

    invalid_plan = {"steps": []}
    is_valid, errors = validate_planner_execution_plan(invalid_plan)
    assert is_valid is False
    assert "zero steps" in errors[0]


def test_missing_executable_entity_validation():
    plan_with_unbound_placeholder = {
        "steps": [
            {
                "step_number": 1,
                "command": "tasklist | findstr /I {entities.executable}",
                "output_parse_instruction": "Inspect output."
            }
        ]
    }
    # Test with missing executable in entities
    is_valid, errors = validate_planner_execution_plan(
        execution_plan=plan_with_unbound_placeholder,
        entities={"hostname": "LAB-PC-010"}
    )
    assert is_valid is False
    assert any("executable" in err.lower() or "un-bound" in err.lower() for err in errors)


def test_unified_planner_agent_node():
    from agents.planner.node import planner_agent
    state = {
        "intent": "Account Unlock Procedure",
        "category": "logins",
        "ticket_raw": "Unlock my account for email pradeepnaveen930@gmail.com",
        "entities": {"email": "pradeepnaveen930@gmail.com", "user_id": "usr_99812"},
        "matched_file_path": "logins/SOP-Account-Unlock-Procedure-001.md",
        "sop_source": "okf_playbook",
        "audit_log": []
    }
    cmd = planner_agent(state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update.get("plan_valid") is True
    assert cmd.update.get("execution_plan") is not None
    assert len(cmd.update.get("execution_plan", {}).get("steps", [])) == 4




