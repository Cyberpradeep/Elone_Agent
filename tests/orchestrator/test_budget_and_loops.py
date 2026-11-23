"""Tests for Resource Budgets, Latency Timeouts & Remediation Loop Breaker."""

import time
import pytest
from contracts.state import EngineStateEnum
from contracts.policy import RiskLevelEnum, EnvironmentEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPReference
from orchestrator.budgets import (
    RunBudget,
    BudgetTracker,
    execute_with_timeout,
)
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.stubs import MockExecutorWorker, MockVerifierWorker
from orchestrator.state_graph import (
    ExecutionModeEnum,
    create_orchestrator_graph,
)


def test_budget_tracker_accounting():
    """Verify BudgetTracker token accumulation and limit checking."""
    tracker = BudgetTracker()
    tracker.record_tokens(10_000)
    assert tracker.tokens_used == 10_000

    budget = RunBudget(max_tokens=20_000, max_duration_seconds=60.0)
    ok, err = tracker.check_limits(budget)
    assert ok is True
    assert err is None

    # Exceed tokens
    tracker.record_tokens(15_000)
    ok, err = tracker.check_limits(budget)
    assert ok is False
    assert "Token budget exceeded" in err


def test_node_latency_timeout_fast_function():
    """Verify fast functions return cleanly within timeout budget."""
    def fast_op(x, y):
        return x + y

    res = execute_with_timeout(fast_op, 10, 20, timeout_seconds=1.0)
    assert res == 30


def test_node_latency_timeout_aborts_slow_function():
    """Verify hung/stalled nodes trigger AGENT_TIMEOUT (Edge Case 11)."""
    def stalling_op():
        time.sleep(1.0)
        return "stalled"

    with pytest.raises(TimeoutError, match="AGENT_TIMEOUT"):
        execute_with_timeout(stalling_op, timeout_seconds=0.1)


def test_remediation_loop_breaker_trips_after_two_replans():
    """Proves verification failures break loop after 2 replans -> NEEDS_HUMAN (Edge Case 35)."""
    executor = MockExecutorWorker()
    # Always fail verification to trigger replan loop
    verifier = MockVerifierWorker(default_passed=False, default_message="Service failed healthcheck")
    cp = SqliteCheckpointer(":memory:")
    budget = RunBudget(max_replan_attempts=2)

    graph = create_orchestrator_graph(
        checkpointer=cp,
        interrupt_on_approval=False,
        executor=executor,
        verifier=verifier,
        budget=budget,
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
        risk_level=RiskLevelEnum.LEVEL_1_READONLY,  # Readonly so it executes autonomously
        requires_approval=False,
    )
    plan = ExecutionPlan.create(issue_id="INC-3301", sop=sop, steps=[step]).model_dump(mode="json")

    config = {"configurable": {"thread_id": "thread-replan-loop-1"}}
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-3301",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Loop Test"},
            "plan": plan,
        },
        config=config,
    )

    # State machine must escalate to NEEDS_HUMAN rather than looping infinitely
    assert final_state["workflow_state"] == EngineStateEnum.NEEDS_HUMAN.value
    assert final_state["replan_attempts"] == 2
    assert "Remediation loop breaker" in final_state["error_message"]
    cp.close()


def test_token_budget_exceeded_halts_execution():
    """Proves exceeding global token budget transitions to STOPPED_BUDGET_EXCEEDED (Edge Case 36)."""
    executor = MockExecutorWorker()
    cp = SqliteCheckpointer(":memory:")
    budget = RunBudget(max_tokens=1_000)

    graph = create_orchestrator_graph(
        checkpointer=cp,
        interrupt_on_approval=False,
        executor=executor,
        budget=budget,
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
        risk_level=RiskLevelEnum.LEVEL_1_READONLY,
        requires_approval=False,
    )
    plan = ExecutionPlan.create(issue_id="INC-3302", sop=sop, steps=[step]).model_dump(mode="json")

    config = {"configurable": {"thread_id": "thread-budget-token-1"}}
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-3302",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Budget Test"},
            "plan": plan,
            "tokens_used": 5_000,  # Exceeds max_tokens (1,000)
        },
        config=config,
    )

    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_BUDGET_EXCEEDED.value
    assert "token budget exceeded" in final_state["error_message"].lower()
    assert len(executor.invocations) == 0  # No tool execution occurred
    cp.close()
