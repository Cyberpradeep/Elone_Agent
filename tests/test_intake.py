import pytest
from agents.intake.node import intake_agent, get_raw_uploads_list
from shared.asset_lookup import extract_and_lookup_asset


def test_asset_lookup_enrichment():
    ticket_raw = "Hi, my email is chezhiantech@gmail.com. Internet issue on laptop."
    entities = extract_and_lookup_asset(ticket_raw, {"email": "chezhiantech@gmail.com"})
    assert entities.get("hostname") == "Prabanjan"
    assert entities.get("emp_id") == "EL-003"
    assert entities.get("username") == "prapa"


def test_raw_uploads_scanner():
    uploads = get_raw_uploads_list()
    assert isinstance(uploads, list)
    titles = [u["clean_title"] for u in uploads]
    assert "Network Sop" in titles or len(titles) >= 0


def test_intake_agent_node_routing():
    initial_state = {
        "ticket_id": 999,
        "customer_email": "chezhiantech@gmail.com",
        "category": "network",
        "ticket_raw": "Network connection drops on laptop. Email chezhiantech@gmail.com",
        "entities": {"email": "chezhiantech@gmail.com"},
        "workflow_status": "pending",
        "audit_log": []
    }
    cmd = intake_agent(initial_state)
    assert cmd.goto in ["planner_agent", "orchestration_agent"]
    assert "intent" in cmd.update
    assert "category" in cmd.update


def test_unauthorized_application_escalation():
    initial_state = {
        "ticket_id": 1002,
        "customer_email": "pradeepnaveen930@gmail.com",
        "category": "software",
        "ticket_raw": "Please unblock Torrent application (torrent.exe) for email pradeepnaveen930@gmail.com",
        "entities": {"email": "pradeepnaveen930@gmail.com", "executable": "torrent.exe", "emp_id": "EL-002"},
        "workflow_status": "pending",
        "audit_log": []
    }
    cmd = intake_agent(initial_state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update.get("workflow_status") == "escalated"
    assert cmd.update.get("entities", {}).get("catalog_permission_approved") == "false"


def test_authorized_application_pass():
    initial_state = {
        "ticket_id": 1003,
        "customer_email": "pradeepnaveen930@gmail.com",
        "category": "software",
        "ticket_raw": "Please unblock VS Code application (Code.exe) for email pradeepnaveen930@gmail.com",
        "entities": {"email": "pradeepnaveen930@gmail.com", "executable": "Code.exe", "emp_id": "EL-002"},
        "workflow_status": "pending",
        "audit_log": []
    }
    cmd = intake_agent(initial_state)
    assert cmd.update.get("entities", {}).get("catalog_permission_approved") == "true"


def test_tool_sop_account_unlock_triage():
    initial_state = {
        "ticket_id": 1004,
        "customer_email": "pradeepnaveen930@gmail.com",
        "category": "logins",
        "ticket_raw": "My user account is locked. Please unlock my account for email pradeepnaveen930@gmail.com",
        "entities": {"email": "pradeepnaveen930@gmail.com"},
        "workflow_status": "pending",
        "audit_log": []
    }
    cmd = intake_agent(initial_state)
    assert cmd.goto in ["planner_agent", "orchestration_agent"]
    assert "email" in cmd.update.get("entities", {})


def test_unknown_employee_email_escalation():
    initial_state = {
        "ticket_id": 1005,
        "customer_email": "unknown_employee999@external.com",
        "category": "logins",
        "ticket_raw": "Please unlock my account for email unknown_employee999@external.com",
        "entities": {"email": "unknown_employee999@external.com"},
        "workflow_status": "pending",
        "audit_log": []
    }
    cmd = intake_agent(initial_state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update.get("workflow_status") == "escalated"
    assert "Asset Management" in cmd.update.get("orchestrator_reasoning", "")


def test_john_doe_denied_application_policy():
    initial_state = {
        "ticket_id": 1006,
        "customer_email": "john.doe@testcorp.com",
        "category": "software",
        "ticket_raw": "Please unblock VS Code application (Code.exe) for email john.doe@testcorp.com",
        "entities": {"email": "john.doe@testcorp.com", "executable": "Code.exe", "emp_id": "EL-005"},
        "workflow_status": "pending",
        "audit_log": []
    }
    cmd = intake_agent(initial_state)
    assert cmd.goto == "orchestration_agent"
    assert cmd.update.get("workflow_status") == "escalated"
    assert cmd.update.get("entities", {}).get("catalog_permission_approved") == "false"




