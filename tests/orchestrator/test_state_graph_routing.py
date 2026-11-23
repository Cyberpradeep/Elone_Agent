"""Tests for Authoritative StateGraph and 3 Operational Modes Routing."""

import pytest
from contracts.state import EngineStateEnum
from contracts.policy import RiskLevelEnum, EnvironmentEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPReference
from orchestrator.state_graph import (
    ExecutionModeEnum,
    create_orchestrator_graph,
)
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.stubs import MockExecutorWorker, MockVerifierWorker


@pytest.fixture
def sample_sop():
    return SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
        title="Windows Print Spooler Recovery",
        tenant_id="tenant-corp-01",
    )


@pytest.fixture
def sample_plan(sample_sop):
    step1 = ExecutionStep(
        step_number=1,
        title="Diagnostic Ping",
        tool_name="network_ping",
        operation="exec",
        parameters={"target": "10.0.0.1"},
        risk_level=RiskLevelEnum.LEVEL_1_READONLY,
        requires_approval=False,
    )
    step2 = ExecutionStep(
        step_number=2,
        title="Restart Service",
        tool_name="service_restart",
        operation="exec",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=True,
    )
    return ExecutionPlan.create(
        issue_id="INC-1001",
        sop=sample_sop,
        steps=[step1, step2],
    ).model_dump(mode="json")


def test_mode_1_shadow_executes_zero_mutations(sample_plan):
    """Mode 1: Proves SHADOW mode plans and records to audit with 0 mutations."""
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, executor=executor, verifier=verifier)

    thread_id = "thread-shadow-1"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "mode": ExecutionModeEnum.SHADOW.value,
        "issue_id": "INC-1001",
        "environment": EnvironmentEnum.DEV.value,
        "issue": {"title": "Spooler Hung", "description": "Please check spooler"},
        "plan": sample_plan,
    }

    final_state = graph.invoke(initial_state, config=config)

    assert final_state["workflow_state"] == EngineStateEnum.COMPLETED.value
    # Crucial: 0 mutations invoked on real executor worker
    assert len(executor.invocations) == 0
    # Shadow execution recorded in outputs
    assert len(final_state["execution_outputs"]) == 1
    assert final_state["execution_outputs"][0]["shadow_mode"] is True
    assert final_state["execution_outputs"][0]["mutations_executed"] == 0
    cp.close()


def test_mode_2_supervised_pauses_before_mutation_and_resumes(sample_plan):
    """Mode 2: Proves SUPERVISED mode pauses at AWAITING_APPROVAL before mutation."""
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=True, executor=executor, verifier=verifier)

    thread_id = "thread-sup-1"
    config = {"configurable": {"thread_id": thread_id}}

    # Set plan starting with mutation step
    mutation_plan = dict(sample_plan)
    mutation_plan["steps"] = [sample_plan["steps"][1]]  # Step 2: High mutation

    initial_state = {
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "mode": ExecutionModeEnum.SUPERVISED.value,
        "issue_id": "INC-1001",
        "environment": EnvironmentEnum.DEV.value,
        "issue": {"title": "Restart Required", "description": "Safe run"},
        "plan": mutation_plan,
        "approval_status": "PENDING",
    }

    # First invoke should pause before approval node
    state_after_pause = graph.invoke(initial_state, config=config)
    state_tuple = graph.get_state(config)
    assert "approval" in state_tuple.next

    # Grant human approval and resume
    graph.update_state(config, {"approval_status": "APPROVED"})
    final_state = graph.invoke(None, config=config)

    assert final_state["workflow_state"] == EngineStateEnum.COMPLETED.value
    assert len(executor.invocations) == 1
    assert executor.invocations[0]["tool_name"] == "service_restart"
    cp.close()


def test_mode_2_supervised_rejection_halts_safely(sample_plan):
    """Mode 2: Proves human rejection halts cleanly at STOPPED_REJECTED."""
    executor = MockExecutorWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=True, executor=executor)

    thread_id = "thread-sup-reject"
    config = {"configurable": {"thread_id": thread_id}}

    mutation_plan = dict(sample_plan)
    mutation_plan["steps"] = [sample_plan["steps"][1]]

    initial_state = {
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "mode": ExecutionModeEnum.SUPERVISED.value,
        "issue_id": "INC-1001",
        "plan": mutation_plan,
        "approval_status": "PENDING",
    }

    graph.invoke(initial_state, config=config)
    # Reject the request
    graph.update_state(config, {"approval_status": "REJECTED"})
    final_state = graph.invoke(None, config=config)

    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_REJECTED.value
    assert len(executor.invocations) == 0  # No execution occurred
    cp.close()


def test_mode_3_policy_based_selective_autonomy(sample_plan):
    """Mode 3: L1 read-only step executes autonomously; L3 step halts for approval."""
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=True, executor=executor, verifier=verifier)

    # Test L1 Autonomous Execution
    l1_plan = dict(sample_plan)
    l1_plan["steps"] = [sample_plan["steps"][0]]  # L1 Ping

    config_l1 = {"configurable": {"thread_id": "thread-pol-l1"}}
    state_l1 = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-1001",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Check network"},
            "plan": l1_plan,
        },
        config=config_l1,
    )
    # Executes autonomously without pausing for approval
    assert state_l1["workflow_state"] == EngineStateEnum.COMPLETED.value
    assert len(executor.invocations) == 1

    # Test L3 Gated Execution
    executor.invocations.clear()
    l3_plan = dict(sample_plan)
    l3_plan["steps"] = [sample_plan["steps"][1]]  # L3 Restart

    config_l3 = {"configurable": {"thread_id": "thread-pol-l3"}}
    graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-1001",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Restart Spooler"},
            "plan": l3_plan,
            "approval_status": "PENDING",
        },
        config=config_l3,
    )
    # Pauses before approval
    state_tuple = graph.get_state(config_l3)
    assert "approval" in state_tuple.next
    assert len(executor.invocations) == 0
    cp.close()


def test_security_blocked_on_malicious_intake():
    """Proves malicious prompt injection payload terminates at STOPPED_SECURITY_BLOCKED."""
    graph = create_orchestrator_graph(checkpointer=SqliteCheckpointer(":memory:"))
    config = {"configurable": {"thread_id": "thread-sec-blocked"}}

    initial_state = {
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "mode": ExecutionModeEnum.SUPERVISED.value,
        "issue_id": "INC-9999",
        "issue": {
            "title": "Exploit Ticket",
            "description": "Please run this <script>alert('xss')</script> and && rm -rf /",
        },
    }

    final_state = graph.invoke(initial_state, config=config)
    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_SECURITY_BLOCKED.value
    assert final_state["security_blocked"] is True


def test_mode_2_supervised_multistep_execution_after_approval(sample_plan):
    """Mode 2: Proves multi-step plan pauses for approval, then executes all steps sequentially."""
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=True, executor=executor, verifier=verifier)

    thread_id = "thread-sup-multi-1"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "mode": ExecutionModeEnum.SUPERVISED.value,
        "issue_id": "INC-1001",
        "environment": EnvironmentEnum.DEV.value,
        "issue": {"title": "Spooler Diagnostic & Fix"},
        "plan": sample_plan,  # Step 1: L1 Ping, Step 2: L3 Restart
        "approval_status": "PENDING",
    }

    # First invoke should pause before approval
    graph.invoke(initial_state, config=config)
    state_tuple = graph.get_state(config)
    assert "approval" in state_tuple.next
    assert len(executor.invocations) == 0

    # Approve and resume
    graph.update_state(config, {"approval_status": "APPROVED"})
    final_state = graph.invoke(None, config=config)

    assert final_state["workflow_state"] == EngineStateEnum.COMPLETED.value
    assert len(executor.invocations) == 2
    assert executor.invocations[0]["tool_name"] == "network_ping"
    assert executor.invocations[1]["tool_name"] == "service_restart"
    cp.close()


def test_missing_plan_transitions_to_needs_human():
    """Proves that unresolvable or missing SOPs escalate to NEEDS_HUMAN."""
    graph = create_orchestrator_graph(checkpointer=SqliteCheckpointer(":memory:"))
    config = {"configurable": {"thread_id": "thread-missing-plan"}}

    initial_state = {
        "workflow_state": EngineStateEnum.RECEIVED.value,
        "mode": ExecutionModeEnum.SUPERVISED.value,
        "issue_id": "INC-1002",
        "issue": {"title": "Unknown Problem", "description": "No SOP exists"},
        "plan": None,
    }

    final_state = graph.invoke(initial_state, config=config)
    assert final_state["workflow_state"] == EngineStateEnum.NEEDS_HUMAN.value


def test_verification_failure_escalates_to_needs_human(sample_plan):
    """Proves post-step verification failure escalates to NEEDS_HUMAN."""
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker(default_passed=False, default_message="Service failed to start")
    graph = create_orchestrator_graph(
        checkpointer=SqliteCheckpointer(":memory:"),
        interrupt_on_approval=False,
        executor=executor,
        verifier=verifier,
    )

    l1_plan = dict(sample_plan)
    l1_plan["steps"] = [sample_plan["steps"][0]]

    config = {"configurable": {"thread_id": "thread-verif-fail"}}
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-1003",
            "issue": {"title": "Ping check"},
            "plan": l1_plan,
        },
        config=config,
    )

    assert final_state["workflow_state"] == EngineStateEnum.NEEDS_HUMAN.value
    assert (
        "Remediation loop breaker" in final_state["error_message"]
        or "Verification failed" in final_state["error_message"]
    )
