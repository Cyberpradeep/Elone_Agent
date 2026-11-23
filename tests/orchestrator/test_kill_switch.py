"""Tests for Emergency Kill Switch Subsystem."""

import pytest
from contracts.state import EngineStateEnum
from contracts.policy import RiskLevelEnum, EnvironmentEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPReference
from orchestrator.kill_switch import KillSwitch, GLOBAL_KILL_SWITCH
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.stubs import MockExecutorWorker
from orchestrator.state_graph import (
    ExecutionModeEnum,
    create_orchestrator_graph,
)


@pytest.fixture(autouse=True)
def reset_kill_switch():
    """Reset global kill switch singleton before and after each test."""
    GLOBAL_KILL_SWITCH.reset_all()
    yield
    GLOBAL_KILL_SWITCH.reset_all()


def test_kill_switch_unit():
    """Verify KillSwitch instance unit controls."""
    ks = KillSwitch()
    assert not ks.is_global_engaged()
    assert not ks.is_thread_stopped("t1")

    # Thread stop
    ks.engage_thread("t1")
    assert ks.is_thread_stopped("t1")
    assert not ks.is_thread_stopped("t2")
    ks.disengage_thread("t1")
    assert not ks.is_thread_stopped("t1")

    # Global stop
    ks.engage_global()
    assert ks.is_global_engaged()
    assert ks.is_thread_stopped("any-thread")
    ks.disengage_global()
    assert not ks.is_global_engaged()


def test_kill_switch_halts_execution_immediately():
    """Proves engaging kill switch aborts execution before the mutation tool runs."""
    executor = MockExecutorWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=False, executor=executor)

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="a" * 64,
        title="Spooler Fix",
        tenant_id="tenant-1",
    )
    step = ExecutionStep(
        step_number=1,
        title="Restart Service",
        tool_name="service_restart",
        operation="exec",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=False,
    )
    plan = ExecutionPlan.create(issue_id="INC-9901", sop=sop, steps=[step]).model_dump(mode="json")

    thread_id = "thread-kill-test-1"
    config = {"configurable": {"thread_id": thread_id}}

    # Engage thread kill switch before execution
    GLOBAL_KILL_SWITCH.engage_thread("INC-9901")

    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-9901",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Kill test"},
            "plan": plan,
            "approval_status": "APPROVED",
        },
        config=config,
    )

    # State transitions to STOPPED_KILL_SWITCH
    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_KILL_SWITCH.value
    assert final_state["kill_switch_engaged"] is True
    # Zero tool mutations executed
    assert len(executor.invocations) == 0
    cp.close()
