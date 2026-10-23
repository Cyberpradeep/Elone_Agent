import json
import uuid
# pyrefly: ignore [missing-import]
from langgraph.types import Command
from typing import Literal

from shared.state import SupportState


def escalation_agent(state: SupportState) -> Command[Literal["summarization_agent"]]:
    """Escalation Agent Node: Constructs a structured L2 Engineering Escalation Ticket."""
    ticket_id = state.get("ticket_id") or "1000"
    intent = state.get("intent") or "System Troubleshooting"
    category = state.get("category") or "general"
    priority = state.get("priority") or "normal"
    reason = state.get("orchestrator_reasoning") or state.get("execution_reasoning") or "Workflow explicitly escalated or retry budget exhausted."
    
    entities = state.get("entities") or {}
    hostname = entities.get("hostname", "target machine")
    customer_email = state.get("customer_email") or entities.get("email", "unknown_user")
    
    plan = state.get("execution_plan") or {}
    steps = plan.get("steps") or []
    step_idx = state.get("current_step_index", 0)
    failed_step = steps[step_idx] if step_idx < len(steps) else {}
    
    last_command = state.get("last_executed_command") or failed_step.get("command") or "(none)"
    last_exit_code = state.get("last_executed_exit_code") if state.get("last_executed_exit_code") is not None else "N/A"

    # Build L2 Handover Markdown Ticket
    escalation_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
    handover_markdown = f"""# L2/L3 TECHNICAL ESCALATION HANDOVER TICKET [{escalation_id}]

## 1. TICKET & WORKSTATION SUMMARY
- **Ticket ID**: #{ticket_id}
- **Customer Email**: {customer_email}
- **Target Hostname**: {hostname}
- **Intent Category**: {category.upper()} | Priority: {priority.upper()}
- **Escalation Reason**: {reason}

## 2. AUTOMATION HALT CONTEXT
- **Halted Step Number**: Step {step_idx + 1} of {len(steps)}
- **Step Description**: {failed_step.get('sop_step_description', 'N/A')}
- **Last Executed Command**: `{last_command}` (Exit Code: {last_exit_code})

## 3. EXTRACTED DIAGNOSTIC VARIABLES
```json
{json.dumps(state.get("variables") or {}, indent=2)}
```

## 4. AUDIT TRAJECTORY LOG
{json.dumps(state.get("audit_log", []), indent=2)}

## 5. RECOMMENDED L2 NEXT ACTIONS
- Inspect workstation `{hostname}` manually via RDP/WinRM or Remote Control.
- Review CLI command stdout for step `{last_command}`.
- Verify user permissions or network adapter hardware status.
"""

    payload = {
        "escalation_id": escalation_id,
        "ticket_id": ticket_id,
        "customer_email": customer_email,
        "hostname": hostname,
        "intent": intent,
        "category": category,
        "priority": priority,
        "reason": reason,
        "failed_step_number": step_idx + 1,
        "last_command": last_command,
        "last_exit_code": last_exit_code,
        "variables": state.get("variables") or {},
        "handover_markdown": handover_markdown,
    }

    print(f"\n==================================================")
    print(f"--- [L2 ESCALATION AGENT HANDOVER GENERATED] ---")
    print(f"  Escalation ID: {escalation_id} | Host: {hostname}")
    print(f"  Reason: {reason}")
    print(f"==================================================\n")

    return Command(
        goto="summarization_agent",
        update={
            "escalation_payload": payload,
            "workflow_status": "escalated",
            "audit_log": [f"[Escalation Agent] Formulated L2 Handover Ticket '{escalation_id}' ({reason})"],
        },
    )
