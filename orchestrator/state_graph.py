"""Authoritative LangGraph State Graph & 3-Mode Conditional Routing Engine.

Enforces deterministic transitions according to contracts/state.py and governs
the three operational modes: SHADOW, SUPERVISED, and POLICY_BASED.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, START, END

from contracts.state import EngineStateEnum, validate_transition_or_raise
from contracts.policy import RiskLevelEnum, EnvironmentEnum, evaluate_step_risk
from contracts.plan import ExecutionStep
from hub_security.sanitizer import sanitize_incoming_ticket, wrap_untrusted_data
from orchestrator.stubs import MockExecutorWorker, MockVerifierWorker


class ExecutionModeEnum(str, Enum):
    """The three authoritative operational modes."""

    SHADOW = "SHADOW"
    SUPERVISED = "SUPERVISED"
    POLICY_BASED = "POLICY_BASED"


class EngineState(TypedDict, total=False):
    """Authoritative state payload for LangGraph workflow execution."""

    workflow_state: str
    mode: str
    issue_id: str
    environment: str
    issue: Optional[Dict[str, Any]]
    plan: Optional[Dict[str, Any]]
    current_step_idx: int
    approval_status: Optional[str]  # "PENDING", "APPROVED", "REJECTED"
    execution_outputs: List[Dict[str, Any]]
    verification_results: List[Dict[str, Any]]
    replan_attempts: int
    security_blocked: bool
    kill_switch_engaged: bool
    error_message: Optional[str]


def intake_node(state: EngineState) -> Dict[str, Any]:
    """Triage and sanitize incoming incident issue."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.RECEIVED.value))
    issue = state.get("issue") or {}
    description = issue.get("description", "")
    title = issue.get("title", "")

    # Security check: detect prompt injection or malicious payloads
    combined = f"{title} {description}"
    is_malicious = False
    if "<script" in combined.lower() or "javascript:" in combined.lower() or "&& rm -rf" in combined:
        is_malicious = True

    if is_malicious or state.get("security_blocked", False):
        target = EngineStateEnum.STOPPED_SECURITY_BLOCKED
        validate_transition_or_raise(current, target)
        return {
            "workflow_state": target.value,
            "security_blocked": True,
            "error_message": "Prompt injection or malicious input detected during intake",
        }

    target = EngineStateEnum.TRIAGED
    validate_transition_or_raise(current, target)
    return {
        "workflow_state": target.value,
        "security_blocked": False,
    }


def planner_node(state: EngineState) -> Dict[str, Any]:
    """Validate and bind execution plan to current issue."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.TRIAGED.value))
    plan = state.get("plan")

    if not plan or not plan.get("steps"):
        target = EngineStateEnum.NEEDS_HUMAN
        validate_transition_or_raise(current, target)
        return {
            "workflow_state": target.value,
            "error_message": "No matching SOP or plan steps found for incident",
        }

    target = EngineStateEnum.PLANNED
    validate_transition_or_raise(current, target)
    return {
        "workflow_state": target.value,
        "current_step_idx": 0,
        "execution_outputs": [],
        "verification_results": [],
    }


def policy_node(state: EngineState) -> Dict[str, Any]:
    """Evaluate risk rules and production constraints for execution steps."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.PLANNED.value))
    plan = state.get("plan") or {}
    steps = plan.get("steps", [])
    idx = state.get("current_step_idx", 0)
    env_str = state.get("environment", EnvironmentEnum.DEV.value)
    env = EnvironmentEnum(env_str) if env_str in EnvironmentEnum.__members__ else EnvironmentEnum.DEV

    if idx < len(steps):
        raw_step = steps[idx]
        base_risk = raw_step.get("risk_level", RiskLevelEnum.LEVEL_1_READONLY)
        if isinstance(base_risk, int):
            base_risk = RiskLevelEnum(base_risk)
        decision = evaluate_step_risk(
            step_number=raw_step.get("step_number", idx + 1),
            base_risk=base_risk,
            environment=env,
        )
        raw_step["evaluated_risk"] = decision.evaluated_risk.value
        raw_step["requires_approval"] = decision.requires_approval

    target = EngineStateEnum.POLICY_EVALUATED
    # If looping from VERIFYING -> EXECUTING, POLICY_EVALUATED was already verified
    if current != EngineStateEnum.POLICY_EVALUATED:
        validate_transition_or_raise(current, target)

    return {
        "workflow_state": target.value,
        "plan": plan,
    }


def shadow_node(state: EngineState) -> Dict[str, Any]:
    """Simulate execution in SHADOW mode (0 mutations executed)."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.POLICY_EVALUATED.value))
    target = EngineStateEnum.EXECUTING
    validate_transition_or_raise(current, target)

    plan = state.get("plan") or {}
    shadow_record = {
        "shadow_mode": True,
        "plan_hash": plan.get("plan_hash", ""),
        "mutations_executed": 0,
        "status": "RECORDED_TO_AUDIT",
    }
    outputs = list(state.get("execution_outputs", []))
    outputs.append(shadow_record)

    return {
        "workflow_state": target.value,
        "execution_outputs": outputs,
    }


def approval_node(state: EngineState) -> Dict[str, Any]:
    """Hold execution awaiting explicit human authorization."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.POLICY_EVALUATED.value))
    target = EngineStateEnum.AWAITING_APPROVAL
    validate_transition_or_raise(current, target)
    return {
        "workflow_state": target.value,
        "approval_status": state.get("approval_status", "PENDING"),
    }


def execution_node(state: EngineState, executor: Optional[MockExecutorWorker] = None) -> Dict[str, Any]:
    """Execute the active step via executor worker."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.AWAITING_APPROVAL.value))
    target = EngineStateEnum.EXECUTING
    if current != target:
        validate_transition_or_raise(current, target)

    executor = executor or MockExecutorWorker()
    plan = state.get("plan") or {}
    steps = plan.get("steps", [])
    idx = state.get("current_step_idx", 0)

    outputs = list(state.get("execution_outputs", []))
    if idx < len(steps):
        raw_step = steps[idx]
        step_model = ExecutionStep(
            step_number=raw_step.get("step_number", idx + 1),
            title=raw_step.get("title", f"Step {idx + 1}"),
            tool_name=raw_step.get("tool_name", "generic_tool"),
            operation=raw_step.get("operation", "exec"),
            parameters=raw_step.get("parameters", {}),
            risk_level=RiskLevelEnum(raw_step.get("evaluated_risk", raw_step.get("risk_level", 1))),
            timeout_seconds=raw_step.get("timeout_seconds", 30),
            requires_approval=raw_step.get("requires_approval", False),
        )
        res = executor.execute_step(step_model)
        outputs.append(res)

    return {
        "workflow_state": target.value,
        "execution_outputs": outputs,
    }


def verification_node(state: EngineState, verifier: Optional[MockVerifierWorker] = None) -> Dict[str, Any]:
    """Verify execution outcome and determine step progression."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.EXECUTING.value))
    target = EngineStateEnum.VERIFYING
    validate_transition_or_raise(current, target)

    verifier = verifier or MockVerifierWorker()
    idx = state.get("current_step_idx", 0)
    steps = (state.get("plan") or {}).get("steps", [])

    v_res = verifier.verify_step(step_number=idx + 1)
    results = list(state.get("verification_results", []))
    results.append(v_res)

    mode = state.get("mode", ExecutionModeEnum.SUPERVISED.value)

    if not v_res.get("passed", False):
        final_target = EngineStateEnum.NEEDS_HUMAN
        validate_transition_or_raise(target, final_target)
        return {
            "workflow_state": final_target.value,
            "verification_results": results,
            "error_message": f"Verification failed on step {idx + 1}",
        }

    # If shadow mode or all steps completed
    if mode == ExecutionModeEnum.SHADOW.value or (idx + 1 >= len(steps)):
        final_target = EngineStateEnum.COMPLETED
        validate_transition_or_raise(target, final_target)
        return {
            "workflow_state": final_target.value,
            "verification_results": results,
        }

    # More steps remain -> progress to next step
    loop_target = EngineStateEnum.EXECUTING
    validate_transition_or_raise(target, loop_target)
    return {
        "workflow_state": loop_target.value,
        "current_step_idx": idx + 1,
        "verification_results": results,
    }


def security_blocked_node(state: EngineState) -> Dict[str, Any]:
    """Terminal security stop state."""
    return {"workflow_state": EngineStateEnum.STOPPED_SECURITY_BLOCKED.value}


def rejected_node(state: EngineState) -> Dict[str, Any]:
    """Terminal human rejection stop state."""
    current = EngineStateEnum(state.get("workflow_state", EngineStateEnum.AWAITING_APPROVAL.value))
    target = EngineStateEnum.STOPPED_REJECTED
    validate_transition_or_raise(current, target)
    return {"workflow_state": target.value}


def needs_human_node(state: EngineState) -> Dict[str, Any]:
    """Terminal human escalation state."""
    return {"workflow_state": EngineStateEnum.NEEDS_HUMAN.value}


# --- Conditional Routing Functions ---


def route_after_intake(state: EngineState) -> str:
    """Route based on intake sanitization decision."""
    if state.get("security_blocked") or state.get("workflow_state") == EngineStateEnum.STOPPED_SECURITY_BLOCKED.value:
        return "security_blocked"
    return "planner"


def route_after_planner(state: EngineState) -> str:
    """Route after planning phase."""
    if state.get("workflow_state") == EngineStateEnum.NEEDS_HUMAN.value:
        return "needs_human"
    return "policy"


def route_execution_by_mode(state: EngineState) -> str:
    """Route step execution according to the active mode and evaluated risk."""
    mode = state.get("mode", ExecutionModeEnum.SUPERVISED.value)

    # Mode 1: Shadow Mode (0 mutations executed)
    if mode == ExecutionModeEnum.SHADOW.value:
        return "shadow"

    plan = state.get("plan") or {}
    steps = plan.get("steps", [])

    def step_risk_val(step: Dict[str, Any]) -> int:
        r = step.get("evaluated_risk", step.get("risk_level", 1))
        return r.value if hasattr(r, "value") else int(r)

    # Mode 2: Supervised Mode (any mutation in plan requires approval)
    if mode == ExecutionModeEnum.SUPERVISED.value:
        has_mutation = any(step_risk_val(s) > 1 for s in steps)
        if has_mutation:
            return "approval"
        return "execution"

    # Mode 3: Policy-Based Mode (L1-2 autonomous, L3-4 approval gated)
    if mode == ExecutionModeEnum.POLICY_BASED.value:
        has_high_risk = any(step_risk_val(s) >= 3 for s in steps)
        if has_high_risk:
            return "approval"
        return "execution"

    return "approval"


def route_after_approval(state: EngineState) -> str:
    """Route after human approval pause."""
    status = state.get("approval_status")
    if status == "APPROVED":
        return "execution"
    if status == "REJECTED":
        return "rejected"
    return "approval"


def route_after_verification(state: EngineState) -> str:
    """Route after step verification."""
    wf = state.get("workflow_state")
    if wf == EngineStateEnum.COMPLETED.value:
        return "end"
    if wf == EngineStateEnum.NEEDS_HUMAN.value:
        return "needs_human"
    return "execution"


def create_orchestrator_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    interrupt_on_approval: bool = True,
    executor: Optional[MockExecutorWorker] = None,
    verifier: Optional[MockVerifierWorker] = None,
):
    """Compile and return the authoritative LangGraph orchestrator state machine."""
    workflow = StateGraph(EngineState)

    # Bind workers into node closures
    def bound_execution_node(state: EngineState) -> Dict[str, Any]:
        return execution_node(state, executor=executor)

    def bound_verification_node(state: EngineState) -> Dict[str, Any]:
        return verification_node(state, verifier=verifier)

    # Register nodes
    workflow.add_node("intake", intake_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("policy", policy_node)
    workflow.add_node("shadow", shadow_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("execution", bound_execution_node)
    workflow.add_node("verification", bound_verification_node)
    workflow.add_node("security_blocked", security_blocked_node)
    workflow.add_node("rejected", rejected_node)
    workflow.add_node("needs_human", needs_human_node)

    # Register edges
    workflow.add_edge(START, "intake")
    workflow.add_conditional_edges("intake", route_after_intake, {
        "security_blocked": "security_blocked",
        "planner": "planner",
    })
    workflow.add_conditional_edges("planner", route_after_planner, {
        "needs_human": "needs_human",
        "policy": "policy",
    })
    workflow.add_conditional_edges("policy", route_execution_by_mode, {
        "shadow": "shadow",
        "approval": "approval",
        "execution": "execution",
    })
    workflow.add_edge("shadow", "verification")
    workflow.add_conditional_edges("approval", route_after_approval, {
        "execution": "execution",
        "rejected": "rejected",
        "approval": "approval",
    })
    workflow.add_edge("execution", "verification")
    workflow.add_conditional_edges("verification", route_after_verification, {
        "end": END,
        "needs_human": "needs_human",
        "execution": "execution",
    })
    workflow.add_edge("security_blocked", END)
    workflow.add_edge("rejected", END)
    workflow.add_edge("needs_human", END)

    interrupt_nodes = ["approval"] if interrupt_on_approval else []
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes if interrupt_nodes else None,
    )
