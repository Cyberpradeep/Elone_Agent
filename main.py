import uuid
# pyrefly: ignore [missing-import]
from langgraph.types import Command
from graph import graph
from shared.tool_catalog import TOOL_CATALOG
from shared.tracing import setup_observability_tracing

SAMPLE_TICKET = {
    "ticket_id": 1001,
    "customer_email": "pradeepnaveen930@gmail.com",
    "category": "software",
    "ticket_raw": "in my windows lap the notepad is unresponsive",
    "entities": {"email": "pradeepnaveen930@gmail.com"},
}


def run_ticket(ticket: dict):
    # Initialize Arize Phoenix Local Observability Dashboard
    setup_observability_tracing()

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    initial_state = {
        "ticket_id": ticket["ticket_id"],
        "customer_email": ticket.get("customer_email"),
        "category": ticket.get("category"),
        "ticket_raw": ticket["ticket_raw"],
        "entities": ticket.get("entities"),
        "tool_catalog": TOOL_CATALOG,
        "replan_attempts": 0,
        "sop_fetch_attempts": 0,
        "execution_retry_attempts": 0,
        "clarification_attempts": 0,
        "workflow_status": "pending",
        "audit_log": [],
    }

    final_state = graph.invoke(initial_state, config=config)

    while True:
        # Check if the agent requires clarification (pre-SOP)
        if final_state.get("workflow_status") == "need_clarification":
            ui = final_state.get("clarification_ui")
            if ui and ui.get("type") == "dropdown":
                fields = ui.get("fields", [])
                user_reply = {}
                for field in fields:
                    print(f"\n[L1 AGENT] {field['label']}")
                    options = field["options"]
                    for idx, opt in enumerate(options):
                        print(f"  {idx + 1}. {opt['label']}")
                    
                    while True:
                        try:
                            choice = int(input("Select option (number): ").strip())
                            if 1 <= choice <= len(options):
                                selected_val = options[choice - 1]["value"]
                                user_reply[field["name"]] = selected_val
                                break
                            else:
                                print(f"Please enter a number between 1 and {len(options)}")
                        except ValueError:
                            print("Please enter a valid number")
                
                # Check if "other" is selected
                if user_reply.get("environment") == "other" or user_reply.get("intent") == "other":
                    print("\nPlease describe your issue in detail:")
                    custom_desc = input("Describe: ").strip()
                    enriched_ticket_raw = f"{final_state['ticket_raw']}\nCustomer stated: Other issue. Description: {custom_desc}"
                    new_state = {
                        "intent": "other",
                        "environment": "other",
                        "ticket_raw": enriched_ticket_raw,
                        "workflow_status": "in_progress",
                        "sop": None,
                        "execution_plan": None,
                        "plan_valid": None,
                        "validator_result": None,
                        "clarification_question": None,
                        "clarification_ui": None,
                    }
                else:
                    new_state = {
                        "intent": user_reply["intent"],
                        "environment": user_reply["environment"],
                        "workflow_status": "in_progress",
                        "sop": None,
                        "execution_plan": None,
                        "plan_valid": None,
                        "validator_result": None,
                        "clarification_question": None,
                        "clarification_ui": None,
                    }
                
                final_state = graph.invoke(new_state, config=config)
                continue
            else:
                question = final_state.get("user_response", "Please provide more details.")
                print(f"\n[L1 AGENT]: {question}")
                user_reply = input("Customer: ").strip()
                enriched_ticket_raw = final_state["ticket_raw"] + f"\nCustomer Clarification: {user_reply}"
                new_state = {
                    "ticket_raw": enriched_ticket_raw,
                    "workflow_status": "in_progress",
                    "sop": None,
                    "execution_plan": None,
                    "plan_valid": None,
                    "validator_result": None,
                    "clarification_question": None,
                    "clarification_ui": None,
                }
                final_state = graph.invoke(new_state, config=config)
                continue

        state_snapshot = graph.get_state(config)

        if not state_snapshot.next:
            break

        if "execution_agent" in state_snapshot.next:
            current_state = state_snapshot.values
            plan = current_state.get("execution_plan", {})
            steps = plan.get("steps", [])
            step_idx = current_state.get("current_step_index", 0)

            # Execution now re-enters this node once per step. Only ask for
            # human approval before step 1 of a plan -- steps 2..N auto-continue
            # as long as each one keeps passing Execution Result Agent's
            # per-step verification.
            if step_idx > 0:
                step_res = current_state.get("execution_results", {}).get(step_idx, "")
                if isinstance(step_res, dict):
                    stdout_str = step_res.get("stdout", "")
                else:
                    stdout_str = str(step_res)
                stdout_preview = stdout_str[:150].replace("\n", " ")
                print(f"\n[STEP {step_idx}/{len(steps)} COMPLETED]")
                print(f"  Command Output: {stdout_preview}...")
                print(f"  Extracted Variables: {current_state.get('variables')}")
                print(f"  Next Action: {current_state.get('next_action')} -> Auto-continuing to Step {step_idx + 1}...")
                final_state = graph.invoke(None, config=config)
                continue

            print("\n" + "="*60)
            print("[PAUSE]  HUMAN IN THE LOOP: Execution Approval Required")
            print("="*60)
            print("The following steps are about to be executed:")
            for step in steps:
                step_num = step.get("step_number", "")
                step_type = step.get("step_type") or "command"
                step_desc = step.get("sop_step_description") or step.get("description") or "Execute Step"
                danger_str = f" [DANGEROUS: {step.get('danger_warning')}]" if step.get("is_dangerous") else ""
                print(f"  Step {step_num}: [{step_type}] {step_desc}{danger_str}")
                cmd = step.get("command") or step.get("fallback_command")
                if cmd:
                    print(f"         Command: {cmd} ({step.get('shell', 'cmd')})")
            print("="*60)

            user_input = input("Approve execution? (y/n): ").strip().lower()

            if user_input == 'y':
                print("\n>> Resuming execution...")
                final_state = graph.invoke(None, config=config)
            else:
                reason = input("Reason for rejection: ")
                print("\n[REJECTED] Execution cancelled by user. Routing to escalation...")
                print(f"[REASON]: {reason}")

                # Update the state and simulate that execution_agent completed.
                # This bypasses re-triggering the interrupt_before breakpoint on execution_agent.
                graph.update_state(
                    config,
                    {
                        "workflow_status": "escalated",
                        "next_action": "ESCALATE",
                        "audit_log": [f"[HITL] User rejected the plan. [REASON] : {reason}"],
                        "is_human_rejected": True
                    },
                    as_node="execution_agent"
                )

                # Resume execution by forcing a jump directly to the escalation agent
                final_state = graph.invoke(
                    Command(goto="escalation_agent"),
                    config=config
                )
                break

    print("\n--- USER RESPONSE ---")
    user_resp = final_state.get("customer_ticket_reply") or final_state.get("user_response") or ""
    print(user_resp.replace("→", "->").replace("↓", "v").replace("▶", ">").replace("◀", "<").encode('ascii', errors='replace').decode('ascii'))
    print("\n--- WORKFLOW STATUS ---")
    print(final_state.get("workflow_status"))
    print("\n--- AUDIT LOG  ---")
    for entry in final_state.get("audit_log", []):
        safe_entry = entry.replace("→", "->").replace("↓", "v").replace("▶", ">").replace("◀", "<")
        print(safe_entry.encode('ascii', errors='replace').decode('ascii'))

    return final_state


if __name__ == "__main__":
    run_ticket(SAMPLE_TICKET)
