import uuid
# pyrefly: ignore [missing-import]
from langgraph.types import Command
from graph import graph


def run_sample_ticket():
    initial_state = {
        "ticket_raw": "I can't login to the Localhost portal, I think my password is wrong",
        "intent": "password_reset",
        "entities": {"user_id": "11", "email": "pradeepnaveen930@gmail.com"},
        "priority": "P3",
        "category": "Access Management",

        "sop": None,
        "knowledge_docs": [],

        "workflow_status": "pending",
        "replan_attempts": 0,
        "sop_fetch_attempts": 0,
        "execution_retry_attempts": 0,
        "clarification_attempts": 0,

        "execution_plan": None,
        "tool_catalog": [],

        "plan_valid": None,
        "validator_result": None,
        "plan_errors": None,

        "execution_results": None,
        "next_action": None,

        "audit_log": [],
    }

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    
    final_state = graph.invoke(initial_state, config=config)

    while True:
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
                print(f"\n> Step {step_idx}/{len(steps)} verified OK -- auto-continuing...")
                final_state = graph.invoke(None, config=config)
                continue
                
            print("\n" + "="*60)
            print("HUMAN IN THE LOOP: Execution Approval Required")
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
                    print(f"         Command: {cmd}")
            print("="*60)
            
            user_input = input("Approve execution? (y/n): ").strip().lower()
            
            if user_input == 'y':
                print("\n[RESUMING] Resuming execution...")
                final_state = graph.invoke(None, config=config)
            else:
                reason = input("Reason for rejection: ")
                print("\n[CANCELLED] Execution cancelled by user. Routing to escalation...")
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

    print("\n--- FINAL STATE ---")
    print("Status:", final_state.get("workflow_status"))
    print("User response:", final_state.get("user_response"))
    print("Escalation payload:", final_state.get("escalation_payload"))

    print("\n--- AUDIT LOG ---")
    for entry in final_state.get("audit_log", []):
        print(entry)


if __name__ == "__main__":
    run_sample_ticket()
