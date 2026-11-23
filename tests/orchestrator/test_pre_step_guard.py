"""Tests for Pre-Mutation Hub Status Re-Check Guard (Rule 5 & Edge Case 4)."""

import pytest
from contracts.state import EngineStateEnum
from contracts.policy import RiskLevelEnum, EnvironmentEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPReference
from hub_client.mock_hub import MockHubService
from orchestrator.pre_step_guard import verify_pre_step_guard
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.stubs import MockExecutorWorker
from orchestrator.state_graph import (
    ExecutionModeEnum,
    create_orchestrator_graph,
)


@pytest.fixture
def hub():
    """Fresh MockHubService fixture."""
    return MockHubService()


def test_verify_pre_step_guard_happy_path(hub):
    """Proves valid published SOP passes pre-step guard check."""
    status = hub.get_sop_status("SOP-WIN-014")
    res = verify_pre_step_guard(
        sop_id="SOP-WIN-014",
        expected_canonical_hash=status["canonical_hash"],
        hub_service=hub,
    )
    assert res.passed is True
    assert "PUBLISHED" in res.reason


def test_verify_pre_step_guard_fails_on_hash_mismatch(hub):
    """Proves modified SOP hash is blocked immediately (Edge Case 4)."""
    res = verify_pre_step_guard(
        sop_id="SOP-WIN-014",
        expected_canonical_hash="wrong_hash_" + "0" * 53,
        hub_service=hub,
    )
    assert res.passed is False
    assert "hash mismatch" in res.reason


def test_verify_pre_step_guard_fails_on_deactivated_sop(hub):
    """Proves deactivated SOP is blocked (Rule 5)."""
    hub.deactivate_sop("SOP-WIN-014")
    status = hub.get_sop_status("SOP-WIN-014")
    res = verify_pre_step_guard(
        sop_id="SOP-WIN-014",
        expected_canonical_hash=status["canonical_hash"],
        hub_service=hub,
    )
    assert res.passed is False
    assert "DEACTIVATED" in res.reason


def test_verify_pre_step_guard_fails_closed_on_hub_outage(hub):
    """Proves Hub unreachable fails closed safely (Rule 7)."""
    hub.set_outage(True)
    res = verify_pre_step_guard(
        sop_id="SOP-WIN-014",
        expected_canonical_hash="any_hash",
        hub_service=hub,
    )
    assert res.passed is False
    assert "Hub unreachable" in res.reason


def test_stategraph_pre_step_guard_blocks_deactivated_sop(hub):
    """Proves StateGraph halts at STOPPED_SECURITY_BLOCKED with 0 mutations executed."""
    hub.deactivate_sop("SOP-WIN-014")
    executor = MockExecutorWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(
        checkpointer=cp,
        interrupt_on_approval=False,
        executor=executor,
        hub_service=hub,
    )

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
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
    plan = ExecutionPlan.create(issue_id="INC-7701", sop=sop, steps=[step]).model_dump(mode="json")

    config = {"configurable": {"thread_id": "thread-guard-1"}}
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-7701",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Restart Spooler"},
            "plan": plan,
            "approval_status": "APPROVED",
        },
        config=config,
    )

    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_SECURITY_BLOCKED.value
    assert final_state["security_blocked"] is True
    assert "DEACTIVATED" in final_state["error_message"]
    # 0 mutations executed
    assert len(executor.invocations) == 0
    cp.close()
