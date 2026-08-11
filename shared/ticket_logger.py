import os
import json
import datetime
from typing import Any, Optional, Dict, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKETS_LOG_DIR = os.path.join(BASE_DIR, "knowledge_base", "logs", "tickets")


def _ensure_dir():
    os.makedirs(TICKETS_LOG_DIR, exist_ok=True)


def format_ticket_log_payload(thread_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Formats a flat LangGraph SupportState dictionary into a structured JSON ticket log schema."""
    state = state or {}
    entities = state.get("entities") or {}
    plan = state.get("execution_plan") or {}
    raw_steps = plan.get("steps") or []
    exec_results = state.get("execution_results") or {}
    exec_exit_codes = state.get("execution_exit_codes") or {}
    variables = state.get("variables") or {}

    current_idx = state.get("current_step_index", 0)

    # Format steps array with rich execution metadata
    formatted_steps = []
    for idx, step in enumerate(raw_steps, start=1):
        step_idx_key = str(idx)
        step_idx_int = idx

        stdout_res = exec_results.get(step_idx_int) or exec_results.get(step_idx_key) or ""
        exit_code_val = exec_exit_codes.get(step_idx_int) or exec_exit_codes.get(step_idx_key)

        status_str = "PENDING"
        if idx <= current_idx or exit_code_val is not None:
            if exit_code_val == 0:
                status_str = "SUCCESS"
            elif exit_code_val is not None and exit_code_val != 0:
                status_str = "FAILED" if state.get("workflow_status") == "escalated" else "RETRY"
            elif idx == current_idx + 1:
                status_str = "IN_PROGRESS"

        formatted_steps.append({
            "step_number": step.get("step_number", idx),
            "description": step.get("sop_step_description") or step.get("description") or f"Step {idx}",
            "step_type": step.get("step_type", "command"),
            "command": step.get("command"),
            "shell": step.get("shell", "powershell"),
            "fallback_command": step.get("fallback_command"),
            "execute_if": step.get("execute_if"),
            "is_dangerous": step.get("is_dangerous", False),
            "danger_warning": step.get("danger_warning"),
            "status": status_str,
            "exit_code": exit_code_val,
            "output": stdout_res,
            "output_variable": step.get("output_variable"),
            "output_parse_instruction": step.get("output_parse_instruction"),
        })

    sop_data = state.get("sop") or {}
    sop_id = sop_data.get("sop_id") if isinstance(sop_data, dict) else "SOP-DYN-000"
    sop_title = sop_data.get("title") if isinstance(sop_data, dict) else state.get("intent", "")

    now_iso = datetime.datetime.now().isoformat()

    log_payload = {
        "thread_id": thread_id,
        "ticket_id": state.get("ticket_id") or thread_id,
        "created_at": state.get("created_at") or now_iso,
        "updated_at": now_iso,
        "workflow_status": state.get("workflow_status", "pending"),
        "resolution_type": state.get("resolution_type"),
        "customer": {
            "email": state.get("customer_email") or entities.get("email"),
            "name": entities.get("employee_name"),
            "emp_id": entities.get("emp_id"),
            "user_id": entities.get("user_id"),
            "device_id": entities.get("device_id"),
        },
        "remote_machine": {
            "hostname": entities.get("hostname", "unknown_host"),
            "target_os": entities.get("target_os") or state.get("environment") or "windows",
            "username": entities.get("username"),
            "ip_address": entities.get("hostname"),
        },
        "issue": {
            "ticket_raw": state.get("ticket_raw", ""),
            "intent": state.get("intent"),
            "category": state.get("category"),
            "priority": state.get("priority"),
            "sop_id": sop_id,
            "sop_title": sop_title,
            "ticket_details_confidence": state.get("ticket_details_confidence"),
            "sop_match_confidence": state.get("sop_match_confidence"),
        },
        "execution_plan": {
            "total_steps": len(raw_steps),
            "current_step_index": current_idx,
            "plan_valid": state.get("plan_valid"),
            "validator_result": state.get("validator_result"),
            "steps": formatted_steps,
        },
        "extracted_variables": variables,
        "entities": entities,
        "clarification": {
            "question": state.get("clarification_question"),
            "ui": state.get("clarification_ui"),
            "attempts": state.get("clarification_attempts", 0),
        },
        "escalation_payload": state.get("escalation_payload"),
        "final_responses": {
            "customer_ticket_reply": state.get("customer_ticket_reply") or state.get("user_response"),
            "internal_ticket_summary": state.get("internal_ticket_summary"),
        },
        "audit_log": state.get("audit_log", []),
    }
    return log_payload


def save_ticket_log(thread_id: str, state: Dict[str, Any]) -> str:
    """Saves ticket state as a structured JSON file under knowledge_base/logs/tickets/."""
    if not thread_id:
        return ""
    _ensure_dir()
    payload = format_ticket_log_payload(thread_id, state)
    filename = f"{thread_id}.json"
    filepath = os.path.join(TICKETS_LOG_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        return filepath
    except Exception as e:
        print(f"[TicketLogger Error] Failed writing log for {thread_id}: {e}")
        return ""


def load_ticket_log(thread_id: str) -> Optional[Dict[str, Any]]:
    """Loads ticket log JSON from disk if present."""
    if not thread_id:
        return None
    _ensure_dir()

    # Try exact match or AGT- prefixed match
    candidates = [
        os.path.join(TICKETS_LOG_DIR, f"{thread_id}.json"),
        os.path.join(TICKETS_LOG_DIR, f"AGT-{thread_id}.json") if not thread_id.startswith("AGT-") else "",
    ]

    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[TicketLogger Error] Failed reading log {path}: {e}")
    return None


def list_saved_tickets() -> List[Dict[str, Any]]:
    """Returns a list of all saved tickets from disk for the UI sidebar queue."""
    _ensure_dir()
    summaries = []
    if not os.path.exists(TICKETS_LOG_DIR):
        return summaries

    for fname in sorted(os.listdir(TICKETS_LOG_DIR), reverse=True):
        if fname.endswith(".json"):
            fpath = os.path.join(TICKETS_LOG_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                issue = data.get("issue") or {}
                customer = data.get("customer") or {}
                exec_plan = data.get("execution_plan") or {}

                ticket_raw = issue.get("ticket_raw") or ""
                short_issue = ticket_raw[:40] + "..." if len(ticket_raw) > 40 else ticket_raw or issue.get("intent") or "Support Request"

                summaries.append({
                    "thread_id": data.get("thread_id"),
                    "ticket_id": data.get("ticket_id"),
                    "issue": short_issue,
                    "ticket_raw": ticket_raw,
                    "customer_email": customer.get("email"),
                    "customer_name": customer.get("name"),
                    "category": issue.get("category", "software"),
                    "priority": issue.get("priority", "medium"),
                    "workflow_status": data.get("workflow_status", "pending"),
                    "current_step_index": exec_plan.get("current_step_index", 0),
                    "total_steps": exec_plan.get("total_steps", 0),
                    "updated_at": data.get("updated_at"),
                })
            except Exception as e:
                print(f"[TicketLogger Warning] Failed reading summary for {fname}: {e}")

    return summaries
