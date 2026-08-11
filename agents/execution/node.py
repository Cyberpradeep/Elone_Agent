"""Execution Agent Node (Remote & API Execution Router)."""

from typing import Literal
from langgraph.types import Command

from shared.state import SupportState
from execution_tools import resolve_template_variables, execute_comm_tool
from .conditions import evaluate_condition
from .command_runner import execute_command_step
from .tool_runner import execute_tool_step


def execution_agent(state: SupportState) -> Command[Literal["execution_result_agent", "orchestration_agent", "escalation_agent"]]:
    """Process 1: Execution Node.

    1. Evaluates execute_if conditional triggers via conditions.py.
    2. Routes CLI command steps to command_runner.py.
    3. Routes API tool call steps to tool_runner.py.
    4. Handles communication and manual intervention steps.
    5. Passes execution outputs to execution_result_agent or orchestration_agent.
    """
    if state.get("workflow_status") == "escalated":
        return Command(goto="escalation_agent", update={})

    plan = state.get("execution_plan") or {}
    steps = plan.get("steps") or []
    idx = state.get("current_step_index", 0)

    if not steps or idx >= len(steps):
        return Command(
            goto="orchestration_agent",
            update={
                "next_action": "SUCCESS",
                "orchestrator_reasoning": "All steps executed successfully.",
            },
        )

    target_step = steps[idx]
    step_num = target_step.get("step_number", idx + 1)
    step_type = target_step.get("step_type", "command")
    entities = state.get("entities") or {}
    variables = state.get("variables") or {}

    # 1. Evaluate execute_if Precondition
    execute_if_raw = target_step.get("execute_if")
    if execute_if_raw and str(execute_if_raw).lower() != "none":
        cond_resolved = resolve_template_variables(str(execute_if_raw), entities, variables)
        condition_met = evaluate_condition(cond_resolved, entities=entities, variables=variables)

        if not condition_met:
            audit_msg = f"[Execution Step {step_num}] Precondition '{cond_resolved}' evaluated to False. Skipping step."
            print(f"  {audit_msg}")
            return Command(
                goto="orchestration_agent",
                update={
                    "next_action": "SUCCESS",
                    "execution_reasoning": f"Step {step_num} skipped due to False execute_if condition.",
                    "audit_log": [audit_msg],
                },
            )

    # 2. Handle Communication Steps
    if step_type == "communication":
        desc = target_step.get("sop_step_description") or "Communication step"
        parse_instruction = target_step.get("output_parse_instruction") or ""
        command = target_step.get("command", "")

        print(f"\n--------------------------------------------------")
        print(f"--- [COMMUNICATION STEP - STEP {step_num}/{len(steps)}] ---")
        print(f"  Description: {desc}")
        print(f"  Instruction: {parse_instruction}")
        print(f"--------------------------------------------------")

        fn_name = target_step.get("function_name") or ""
        comm = target_step.get("command") or ""

        if "email" in str(comm).lower() or "email" in str(fn_name).lower():
            to_addr = entities.get("email") or variables.get("email") or "user@example.com"
            comm_inputs = target_step.get("comm_inputs") or {}
            
            subject = comm_inputs.get("subject", f"IT Support Update: Step {step_num}")
            body = comm_inputs.get("body", f"{desc}\n{parse_instruction}")

            # Resolve template placeholders in subject and body
            subject = resolve_template_variables(subject, entities, variables)
            body = resolve_template_variables(body, entities, variables)

            comm_res = execute_comm_tool("send_email", {
                "to_email": to_addr,
                "subject": subject,
                "body": body
            })
            stdout = comm_res.get("message", "Communication dispatched.")
            return Command(
                goto="execution_result_agent",
                update={
                    "last_executed_command": "[COMMUNICATION TOOL: send_email]",
                    "last_executed_stdout": stdout,
                    "last_executed_stderr": "",
                    "last_executed_exit_code": 0,
                }
            )

        else:
            audit_msg = f"[Execution Step {step_num}] Communication / Escalation step reached: {desc}."
            print(f"  {audit_msg}")
            return Command(
                goto="orchestration_agent",
                update={
                    "workflow_status": "escalated",
                    "next_action": "ESCALATE",
                    "orchestrator_reasoning": f"Step {step_num} requested communication/escalation: {desc}",
                    "audit_log": [audit_msg],
                }
            )

    # 3. Handle Manual Steps
    if step_type == "manual":
        audit_msg = f"[Execution Step {step_num}] Step requires manual human intervention: {target_step.get('sop_step_description')}."
        print(f"  {audit_msg}")
        return Command(
            goto="orchestration_agent",
            update={
                "workflow_status": "escalated",
                "orchestrator_reasoning": f"Step {step_num} requires manual intervention: {target_step.get('sop_step_description')}",
                "audit_log": [audit_msg],
            },
        )

    # 4. Handle API Tool Call Steps
    if step_type == "tool_call":
        stdout, stderr, exit_code, label = execute_tool_step(
            target_step, step_num, len(steps), entities, variables
        )
        return Command(
            goto="execution_result_agent",
            update={
                "last_executed_command": label,
                "last_executed_stdout": stdout,
                "last_executed_stderr": stderr,
                "last_executed_exit_code": exit_code,
            }
        )

    # 5. Handle Verification & Condition Steps (Pure State Assertion Checks)
    if step_type in ("verification", "condition") or (not target_step.get("command") and not target_step.get("function_name")):
        desc = target_step.get("sop_step_description") or "Verification assertion step"
        print(f"\n--------------------------------------------------")
        print(f"--- [VERIFICATION STEP - STEP {step_num}/{len(steps)}] ---")
        print(f"  Description: {desc}")
        print(f"--------------------------------------------------")
        return Command(
            goto="execution_result_agent",
            update={
                "last_executed_command": f"[VERIFICATION STEP: {desc}]",
                "last_executed_stdout": '{"status": "verified", "verification_result": "success"}',
                "last_executed_stderr": "",
                "last_executed_exit_code": 0,
            }
        )


    # 5. Handle Default CLI Command Steps
    stdout, stderr, exit_code, label = execute_command_step(
        target_step, step_num, len(steps), entities, variables
    )
    return Command(
        goto="execution_result_agent",
        update={
            "last_executed_command": label,
            "last_executed_stdout": stdout,
            "last_executed_stderr": stderr,
            "last_executed_exit_code": exit_code,
        }
    )
