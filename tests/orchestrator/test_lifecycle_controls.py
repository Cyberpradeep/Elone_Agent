"""Tests for Runtime Lifecycle Controls (Reset Issue, Cancel, and Handover)."""

import pytest
from contracts.state import EngineStateEnum
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.kill_switch import GLOBAL_KILL_SWITCH
from orchestrator.lifecycle import (
    reset_issue,
    cancel_execution,
    package_human_handover,
)
from langgraph.checkpoint.base import empty_checkpoint


@pytest.fixture(autouse=True)
def reset_kill_switch():
    GLOBAL_KILL_SWITCH.reset_all()
    yield
    GLOBAL_KILL_SWITCH.reset_all()


def test_reset_issue_purges_thread_checkpoints():
    """Proves demo reset_issue completely cleans DB checkpoints and resets to RECEIVED."""
    cp = SqliteCheckpointer(":memory:")
    config = {"configurable": {"thread_id": "thread-demo-reset"}}

    cp_obj = empty_checkpoint()
    cp_obj["id"] = "step-old"
    cp_obj["channel_values"] = {"status": "OLD_STATE"}
    cp_obj["channel_versions"] = {"status": 1}

    cp.put(config, cp_obj, {"writes": {}}, {"status": 1})
    assert cp.get_tuple(config) is not None

    GLOBAL_KILL_SWITCH.engage_thread("thread-demo-reset")
    assert GLOBAL_KILL_SWITCH.is_thread_stopped("thread-demo-reset")

    res = reset_issue("thread-demo-reset", cp)
    assert res["workflow_state"] == EngineStateEnum.RECEIVED.value
    # Checkpoints purged
    assert cp.get_tuple(config) is None
    # Kill switch cleared
    assert not GLOBAL_KILL_SWITCH.is_thread_stopped("thread-demo-reset")
    cp.close()


def test_cancel_execution_engages_thread_kill_switch():
    """Proves cancel_execution engages the kill switch to halt pending steps safely."""
    thread_id = "thread-cancel-1"
    assert not GLOBAL_KILL_SWITCH.is_thread_stopped(thread_id)

    res = cancel_execution(thread_id)
    assert res["cancelled"] is True
    assert res["workflow_state"] == EngineStateEnum.STOPPED_KILL_SWITCH.value
    assert GLOBAL_KILL_SWITCH.is_thread_stopped(thread_id)


def test_package_human_handover():
    """Proves structured packaging of incident context when escalating to NEEDS_HUMAN."""
    state = {
        "workflow_state": EngineStateEnum.VERIFYING.value,
        "current_step_idx": 1,
        "plan": {
            "steps": [
                {"step_number": 1, "title": "Ping Diagnostic"},
                {"step_number": 2, "title": "Restart Database Service"},
            ]
        },
        "execution_outputs": [{"step_number": 1, "stdout": "Ping OK"}],
        "verification_results": [{"step_number": 2, "passed": False, "error": "Connection refused"}],
    }

    handover = package_human_handover(
        thread_id="INC-ESCALATE-1",
        state=state,
        reason="Database failed to restart within 30 seconds",
    )

    assert handover["workflow_state"] == EngineStateEnum.NEEDS_HUMAN.value
    assert handover["thread_id"] == "INC-ESCALATE-1"
    assert handover["failed_step"]["title"] == "Restart Database Service"
    assert len(handover["completed_outputs"]) == 1
    assert "Database failed to restart" in handover["escalation_reason"]
