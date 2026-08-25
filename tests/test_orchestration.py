import pytest
from agents.orchestration.node import orchestration_agent


def test_orchestration_hitl_rejection():
    state = {
        "is_human_rejected": True,
        "workflow_status": "pending",
        "orchestrator_reasoning": "User rejected plan"
    }
    cmd = orchestration_agent(state)
    assert cmd.goto == "escalation_agent"
    assert cmd.update["workflow_status"] == "escalated"


def test_orchestration_circuit_breaker_retry_limit():
    state = {
        "execution_retry_attempts": 3,
        "next_action": "RETRY",
        "workflow_status": "in_progress",
        "execution_plan": {"steps": [{"step_number": 1}]}
    }
    cmd = orchestration_agent(state)
    assert cmd.goto == "escalation_agent"
    assert "retry budget exhausted" in cmd.update["orchestrator_reasoning"]


def test_orchestration_success_advancement():
    state = {
        "current_step_index": 0,
        "next_action": "SUCCESS",
        "execution_plan": {"steps": [{"step_number": 1}, {"step_number": 2}]},
        "execution_retry_attempts": 1
    }
    cmd = orchestration_agent(state)
    assert cmd.goto == "execution_agent"
    assert cmd.update["current_step_index"] == 1
    assert cmd.update["execution_retry_attempts"] == 0


def test_orchestration_completion():
    state = {
        "current_step_index": 1,
        "next_action": "SUCCESS",
        "execution_plan": {"steps": [{"step_number": 1}, {"step_number": 2}]},
    }
    cmd = orchestration_agent(state)
    assert cmd.goto == "summarization_agent"
    assert cmd.update["workflow_status"] == "completed"


def test_orchestration_retry_increment():
    state = {
        "current_step_index": 0,
        "next_action": "RETRY",
        "execution_retry_attempts": 0,
        "execution_plan": {"steps": [{"step_number": 1, "command": "echo test"}]}
    }
    cmd = orchestration_agent(state)
    assert cmd.goto == "execution_agent"
    assert cmd.update["execution_retry_attempts"] == 1
    assert cmd.update["next_action"] is None

