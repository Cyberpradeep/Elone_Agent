"""End-to-End Pilot Simulation & Demonstration Script.

Simulates the complete SOP Execution Engine workflow across:
1. Mode 1: SHADOW Mode (Calibrate SOP, 0 mutations executed)
2. Mode 2: SUPERVISED Mode (HITL pause before mutation, operator Approve -> Executed -> Verified)
3. Mode 2: SUPERVISED Mode (Operator Reject -> Clean stop at STOPPED_REJECTED)
4. Mode 3: POLICY_BASED Mode (L1 Readonly autonomous, L3 Gated)
5. Security Defense: Pre-Mutation Hub Deactivation Guard (Rule 5 & Edge Case 4)
6. Emergency Stop: Global Kill Switch halts pending execution (STOPPED_KILL_SWITCH)
7. Demo Reset: reset_issue() purges SQLite checkpoints back to RECEIVED
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path so script can be run from anywhere
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contracts.state import EngineStateEnum
from contracts.policy import RiskLevelEnum, EnvironmentEnum
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.sop import SOPReference
from hub_client.mock_hub import MockHubService
from orchestrator.checkpointer import SqliteCheckpointer
from orchestrator.stubs import MockExecutorWorker, MockVerifierWorker
from orchestrator.kill_switch import GLOBAL_KILL_SWITCH
from orchestrator.lifecycle import reset_issue
from orchestrator.state_graph import (
    ExecutionModeEnum,
    create_orchestrator_graph,
)

# ANSI terminal formatting
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner(title: str):
    print(f"\n{CYAN}{'=' * 75}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{CYAN}{'=' * 75}{RESET}")


def run_scenario_1_shadow_mode():
    """Scenario 1: SHADOW Mode."""
    print_banner("SCENARIO 1: Mode 1 (SHADOW Mode) - SOP-WIN-014 Calibration")
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, executor=executor, verifier=verifier)

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
        title="Windows Print Spooler Service Recovery",
        tenant_id="tenant-corp-01",
    )
    step1 = ExecutionStep(
        step_number=1,
        title="Diagnostic Status Query",
        tool_name="service_query",
        operation="status",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_1_READONLY,
    )
    step2 = ExecutionStep(
        step_number=2,
        title="Restart Spooler Service",
        tool_name="service_restart",
        operation="restart",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
    )
    plan = ExecutionPlan.create(issue_id="INC-1001", sop=sop, steps=[step1, step2]).model_dump(mode="json")

    thread_id = "thread-demo-shadow"
    config = {"configurable": {"thread_id": thread_id}}

    print(f"[*] Intake: Incident INC-1001 loaded into engine")
    print(f"[*] Planning: Bound to {sop.sop_id} v{sop.version} (Plan Hash: {plan['plan_hash'][:16]}...)")
    print(f"[*] Execution Mode: {BOLD}SHADOW{RESET} (Zero mutations permitted)")

    state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.SHADOW.value,
            "issue_id": "INC-1001",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Spooler Stuck", "description": "Users cannot print"},
            "plan": plan,
        },
        config=config,
    )

    print(f"[+] Final State: {GREEN}{state['workflow_state']}{RESET}")
    print(f"[+] Mutations Executed on Worker: {GREEN}{len(executor.invocations)}{RESET} (Expected: 0)")
    print(f"[+] Audit Entry: {state['execution_outputs'][0]}")
    cp.close()
    assert state["workflow_state"] == EngineStateEnum.COMPLETED.value
    assert len(executor.invocations) == 0


def run_scenario_2_supervised_mode_approval():
    """Scenario 2: SUPERVISED Mode - Human Approval."""
    print_banner("SCENARIO 2: Mode 2 (SUPERVISED Mode) - Human Gating & Approval")
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(
        checkpointer=cp,
        interrupt_on_approval=True,
        executor=executor,
        verifier=verifier,
    )

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
        title="Windows Print Spooler Service Recovery",
        tenant_id="tenant-corp-01",
    )
    step1 = ExecutionStep(
        step_number=1,
        title="Restart Spooler Service",
        tool_name="service_restart",
        operation="restart",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=True,
    )
    plan = ExecutionPlan.create(issue_id="INC-1002", sop=sop, steps=[step1]).model_dump(mode="json")

    thread_id = "thread-demo-sup-approve"
    config = {"configurable": {"thread_id": thread_id}}

    print(f"[*] Intake: Incident INC-1002 loaded")
    print(f"[*] Planning: Step 1 is Level 3 High Mutation ({step1.tool_name})")
    print(f"[*] Dispatching graph invocation...")

    # First invoke should pause before approval
    graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.SUPERVISED.value,
            "issue_id": "INC-1002",
            "environment": EnvironmentEnum.PROD.value,
            "issue": {"title": "Spooler Frozen", "description": "Needs restart"},
            "plan": plan,
            "approval_status": "PENDING",
        },
        config=config,
    )

    state_tuple = graph.get_state(config)
    print(f"[!] {YELLOW}Engine Paused! Next Node: {state_tuple.next}{RESET}")
    print(f"[!] Workflow State in SQLite: {YELLOW}{state_tuple.values['workflow_state']}{RESET}")
    print(f"[*] Operator reviews pending plan and clicks: {GREEN}[ APPROVE ]{RESET}")

    # Resume with approval
    graph.update_state(config, {"approval_status": "APPROVED"})
    final_state = graph.invoke(None, config=config)

    print(f"[+] Final State: {GREEN}{final_state['workflow_state']}{RESET}")
    print(f"[+] Mutations Executed: {GREEN}{len(executor.invocations)}{RESET} ({executor.invocations[0]['tool_name']})")
    print(f"[+] Verification Result: {GREEN}{final_state['verification_results'][0]['evidence']}{RESET}")
    cp.close()
    assert final_state["workflow_state"] == EngineStateEnum.COMPLETED.value
    assert len(executor.invocations) == 1


def run_scenario_3_supervised_mode_rejection():
    """Scenario 3: SUPERVISED Mode - Human Rejection."""
    print_banner("SCENARIO 3: Mode 2 (SUPERVISED Mode) - Operator Rejection")
    executor = MockExecutorWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=True, executor=executor)

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
        title="Windows Print Spooler Service Recovery",
        tenant_id="tenant-corp-01",
    )
    step1 = ExecutionStep(
        step_number=1,
        title="Restart Spooler Service",
        tool_name="service_restart",
        operation="restart",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=True,
    )
    plan = ExecutionPlan.create(issue_id="INC-1003", sop=sop, steps=[step1]).model_dump(mode="json")

    thread_id = "thread-demo-sup-reject"
    config = {"configurable": {"thread_id": thread_id}}

    graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.SUPERVISED.value,
            "issue_id": "INC-1003",
            "environment": EnvironmentEnum.PROD.value,
            "issue": {"title": "Service Check"},
            "plan": plan,
            "approval_status": "PENDING",
        },
        config=config,
    )

    print(f"[!] Paused at AWAITING_APPROVAL")
    print(f"[*] Operator reviews and clicks: {RED}[ REJECT ]{RESET} (Maintenance window closed)")

    graph.update_state(config, {"approval_status": "REJECTED"})
    final_state = graph.invoke(None, config=config)

    print(f"[+] Final State: {RED}{final_state['workflow_state']}{RESET}")
    print(f"[+] Tool Invocations: {GREEN}{len(executor.invocations)}{RESET} (Zero mutations)")
    cp.close()
    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_REJECTED.value
    assert len(executor.invocations) == 0


def run_scenario_4_policy_based_selective_autonomy():
    """Scenario 4: POLICY_BASED Mode - Selective Autonomy."""
    print_banner("SCENARIO 4: Mode 3 (POLICY_BASED Mode) - Selective Autonomy")
    executor = MockExecutorWorker()
    verifier = MockVerifierWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=True, executor=executor, verifier=verifier)

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
        title="Spooler Recovery",
        tenant_id="tenant-corp-01",
    )
    step_l1 = ExecutionStep(
        step_number=1,
        title="Diagnostic Ping",
        tool_name="network_ping",
        operation="ping",
        parameters={"host": "127.0.0.1"},
        risk_level=RiskLevelEnum.LEVEL_1_READONLY,
        requires_approval=False,
    )
    plan = ExecutionPlan.create(issue_id="INC-1004", sop=sop, steps=[step_l1]).model_dump(mode="json")

    config = {"configurable": {"thread_id": "thread-demo-pol-l1"}}
    print(f"[*] Running Level 1 (Read-only) step under POLICY_BASED mode...")
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-1004",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Ping Diagnostic"},
            "plan": plan,
        },
        config=config,
    )

    print(f"[+] Level 1 executed autonomously to: {GREEN}{final_state['workflow_state']}{RESET}")
    print(f"[+] Tool executed: {GREEN}{executor.invocations[0]['tool_name']}{RESET}")
    cp.close()
    assert final_state["workflow_state"] == EngineStateEnum.COMPLETED.value


def run_scenario_5_pre_step_guard_security():
    """Scenario 5: Pre-Mutation Hub Deactivation Guard."""
    print_banner("SCENARIO 5: Security Rule 5 & Edge Case 4 - Pre-Mutation Hub Re-Check")
    hub = MockHubService()
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
        tenant_id="tenant-corp-01",
    )
    step1 = ExecutionStep(
        step_number=1,
        title="Restart Spooler",
        tool_name="service_restart",
        operation="restart",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=False,
    )
    plan = ExecutionPlan.create(issue_id="INC-1005", sop=sop, steps=[step1]).model_dump(mode="json")

    # Simulate Hub admin deactivating SOP while engine was in-flight
    print(f"[!] Simulating Hub event: Admin DEACTIVATES {sop.sop_id} on Hub...")
    hub.deactivate_sop("SOP-WIN-014")

    config = {"configurable": {"thread_id": "thread-demo-guard"}}
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-1005",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Restart"},
            "plan": plan,
            "approval_status": "APPROVED",
        },
        config=config,
    )

    print(f"[+] Security Guard Result: {RED}{final_state['workflow_state']}{RESET}")
    print(f"[+] Security Blocked Flag: {RED}{final_state['security_blocked']}{RESET}")
    print(f"[+] Reason: {YELLOW}{final_state['error_message']}{RESET}")
    print(f"[+] Mutations Executed: {GREEN}{len(executor.invocations)}{RESET} (Expected: 0)")
    cp.close()
    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_SECURITY_BLOCKED.value
    assert len(executor.invocations) == 0


def run_scenario_6_emergency_kill_switch():
    """Scenario 6: Global Emergency Kill Switch."""
    print_banner("SCENARIO 6: Emergency Kill Switch Halts In-Flight Execution")
    executor = MockExecutorWorker()
    cp = SqliteCheckpointer(":memory:")
    graph = create_orchestrator_graph(checkpointer=cp, interrupt_on_approval=False, executor=executor)

    sop = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="5454c02f109395e104ed2f0d38cc557a7f4b2baab15d4bfcf32f7a1ad77918a0",
        title="Spooler Fix",
        tenant_id="tenant-corp-01",
    )
    step1 = ExecutionStep(
        step_number=1,
        title="Restart Spooler",
        tool_name="service_restart",
        operation="restart",
        parameters={"service": "Spooler"},
        risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
        requires_approval=False,
    )
    plan = ExecutionPlan.create(issue_id="INC-1006", sop=sop, steps=[step1]).model_dump(mode="json")

    print(f"[!] Operator triggers Global Emergency Kill Switch...")
    GLOBAL_KILL_SWITCH.engage_global()

    config = {"configurable": {"thread_id": "thread-demo-kill"}}
    final_state = graph.invoke(
        {
            "workflow_state": EngineStateEnum.RECEIVED.value,
            "mode": ExecutionModeEnum.POLICY_BASED.value,
            "issue_id": "INC-1006",
            "environment": EnvironmentEnum.DEV.value,
            "issue": {"title": "Urgent stop"},
            "plan": plan,
            "approval_status": "APPROVED",
        },
        config=config,
    )

    print(f"[+] Final State: {RED}{final_state['workflow_state']}{RESET}")
    print(f"[+] Kill Switch Flag: {RED}{final_state['kill_switch_engaged']}{RESET}")
    print(f"[+] Mutations Executed: {GREEN}{len(executor.invocations)}{RESET} (Expected: 0)")
    GLOBAL_KILL_SWITCH.disengage_global()
    cp.close()
    assert final_state["workflow_state"] == EngineStateEnum.STOPPED_KILL_SWITCH.value
    assert len(executor.invocations) == 0


def run_scenario_7_demo_reset_issue():
    """Scenario 7: Demo Reset Issue."""
    print_banner("SCENARIO 7: Page 3 Demo Reset Control - reset_issue()")
    cp = SqliteCheckpointer(":memory:")
    config = {"configurable": {"thread_id": "thread-demo-reset"}}

    # Seed initial state
    print(f"[*] Seeding thread-demo-reset in SQLite checkpointer...")
    cp.put(
        config,
        {"v": 4, "ts": "now", "id": "s1", "channel_values": {"status": "OLD_STATE"}, "channel_versions": {"status": 1}},
        {"writes": {}},
        {"status": 1},
    )
    assert cp.get_tuple(config) is not None
    print(f"[+] Checkpoint verified in SQLite DB")

    print(f"[*] Calling reset_issue('thread-demo-reset')...")
    res = reset_issue("thread-demo-reset", cp)
    print(f"[+] Reset Response: {GREEN}{res['message']}{RESET}")
    print(f"[+] State in Reset Response: {GREEN}{res['workflow_state']}{RESET}")

    tup = cp.get_tuple(config)
    print(f"[+] Querying SQLite for purged thread: {GREEN}{tup}{RESET} (Expected: None)")
    cp.close()
    assert tup is None
    assert res["workflow_state"] == EngineStateEnum.RECEIVED.value


def main():
    print(f"\n{BOLD}{CYAN}==========================================================================={RESET}")
    print(f"{BOLD}{CYAN}     SOP EXECUTION ENGINE - END-TO-END DEMONSTRATION & DRILL RUNNER        {RESET}")
    print(f"{BOLD}{CYAN}==========================================================================={RESET}")
    print(f"Track: Junior A (Decide & Control) | Target: Module A4 Orchestrator\n")

    start_time = time.time()
    try:
        run_scenario_1_shadow_mode()
        run_scenario_2_supervised_mode_approval()
        run_scenario_3_supervised_mode_rejection()
        run_scenario_4_policy_based_selective_autonomy()
        run_scenario_5_pre_step_guard_security()
        run_scenario_6_emergency_kill_switch()
        run_scenario_7_demo_reset_issue()
        elapsed = time.time() - start_time
        print(f"\n{GREEN}{BOLD}{'=' * 75}{RESET}")
        print(f"{GREEN}{BOLD} ALL 7 END-TO-END SCENARIOS COMPLETED SUCCESSFULLY in {elapsed:.2f}s!{RESET}")
        print(f"{GREEN}{BOLD}{'=' * 75}{RESET}\n")
    except Exception as e:
        print(f"\n{RED}{BOLD}DEMO RUN FAILED: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
