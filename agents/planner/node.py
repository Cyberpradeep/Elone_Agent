"""Unified Planner Agent Node (Combines Discovery + Plan Binding & Variable Resolution)."""

import os
from typing import Literal
# pyrefly: ignore [missing-import]
from langgraph.types import Command

from shared.state import SupportState
from agents.planner.discovery import discover_sop_and_memory_paths
from agents.planner.binder import synthesize_execution_plan_with_deep_cot


def planner_agent(state: SupportState) -> Command[Literal["orchestration_agent"]]:
    """Unified Planner Agent Node (Process 3).

    1. Discovers OKF Playbook & verifies Intake SOP match against ticket intent.
    2. Loads reflection memory rules & device profile quirks.
    3. Validates required entity parameters & binds variable placeholders ({entities.user_id}).
    4. Routes directly to plan_validator (or orchestration_agent if missing required entities).
    """
    intent = state.get("intent", "")
    detailed_description = state.get("detailed_description") or state.get("ticket_raw", "")
    keywords = state.get("keywords") or []
    category = state.get("category") or "other"
    entities = state.get("entities") or {}
    hostname = entities.get("hostname", "")
    sop_source = state.get("sop_source")
    matched_file_path = state.get("matched_file_path")
    environment = state.get("environment") or entities.get("target_os") or "windows"

    print(f"\n==================================================")
    print(f"--- [UNIFIED PLANNER AGENT: DISCOVERY & PLAN SYNTHESIS] ---")
    print(f"  Intent: '{intent}' | Category: '{category}' | Host: '{hostname}'")
    print(f"==================================================")

    # 1. SOP Discovery & Memory Path Resolution (with Intent Verification)
    okf_file_path, metadata, discovery_confidence, reflection_rules, device_quirks = discover_sop_and_memory_paths(
        intent=intent,
        category=category,
        detailed_description=detailed_description,
        keywords=keywords,
        hostname=hostname,
        sop_source=sop_source,
        matched_file_path=matched_file_path
    )

    if not okf_file_path or not metadata:
        audit_msg = f"[Planner Error] Failed to discover or verify OKF playbook for intent '{intent}'."
        print(f"  {audit_msg}")
        return Command(
            goto="orchestration_agent",
            update={
                "sop": {"sop_id": None, "title": None, "steps": ""},
                "execution_plan": None,
                "plan_valid": False,
                "validator_result": "WRONG_SOP",
                "workflow_status": "escalated",
                "plan_feedback": f"No OKF playbook found in knowledge_base for intent '{intent}'",
                "audit_log": [audit_msg],
            },
        )

    sop_id = metadata.get("sop_id", "SOP-DYN-000")
    sop_title = metadata.get("title", intent)
    required_entities = metadata.get("required_entities") or []
    raw_steps = metadata.get("steps") or []

    # API Tool Call playbooks (without OS command steps) do not require a target OS hostname
    has_command_step = any(s.get("step_type") == "command" or s.get("command") for s in raw_steps)
    if not has_command_step and "hostname" in required_entities:
        required_entities = [e for e in required_entities if e != "hostname"]


    # 2. Plan Binding & Variable Placeholder Resolution
    execution_plan, reasoning_chain, is_valid, feedback_str = synthesize_execution_plan_with_deep_cot(
        intent=intent,
        category=category,
        environment=environment,
        hostname=hostname,
        entities=entities,
        sop_id=sop_id,
        sop_title=sop_title,
        raw_sop_steps=raw_steps,
        reflection_rules=reflection_rules,
        device_quirks=device_quirks,
        required_entities=required_entities,
    )

    if not is_valid:
        audit_msg = f"[Planner Error] OKF Playbook '{sop_title}' ({sop_id}) plan binding failed: {feedback_str}"
        print(f"  {audit_msg}")
        return Command(
            goto="orchestration_agent",
            update={
                "sop": {"sop_id": sop_id, "title": sop_title, "steps": okf_file_path},
                "okf_file_path": okf_file_path,
                "execution_plan": execution_plan,
                "plan_valid": False,
                "validator_result": "INVALID_PLAN",
                "workflow_status": "escalated",
                "next_action": "ESCALATE",
                "plan_feedback": feedback_str,
                "audit_log": [audit_msg],
            },
        )

    audit_msg = (
        f"[Planner Complete] Synthesized bound execution plan for SOP '{sop_title}' ({sop_id}) "
        f"at {os.path.basename(okf_file_path)} with {len(execution_plan.get('steps', []))} steps."
    )
    print(f"  {audit_msg}\n")

    return Command(
        goto="orchestration_agent",
        update={

            "sop": {"sop_id": sop_id, "title": sop_title, "steps": okf_file_path},
            "okf_file_path": okf_file_path,
            "execution_plan": execution_plan,
            "relevant_memories": reflection_rules,
            "device_quirks": device_quirks,
            "plan_valid": True,
            "validator_result": "VALID",
            "plan_feedback": feedback_str,
            "audit_log": [audit_msg] + reasoning_chain,
        },
    )
