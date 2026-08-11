import pytest
from agents.summarization.node import summarization_agent, SummarizationOutput, _build_rich_fallback_summary


def test_summarization_output_schema():
    out = SummarizationOutput(
        executive_summary="Executive summary test",
        diagnostic_findings=["Finding 1", "Finding 2"],
        actions_taken=["Action 1"],
        discovered_variables={"ip": "192.168.1.1"},
        recommendations="Recommend test",
        customer_ticket_reply="Hello Semmozhi, we fixed your internet connection.",
        internal_ticket_summary="SOP-NET-001 executed on host Prabanjan with exit code 0.",
        resolution_type="FULLY_RESOLVED"
    )
    assert out.resolution_type == "FULLY_RESOLVED"
    assert "Semmozhi" in out.customer_ticket_reply
    assert "SOP-NET-001" in out.internal_ticket_summary
    assert out.executive_summary == "Executive summary test"
    assert len(out.diagnostic_findings) == 2


def test_summarization_rich_fallback_generator():
    state = {
        "intent": "Network Sop",
        "category": "network",
        "sop": {"sop_id": "SOP-NET-001"},
        "entities": {"hostname": "Prabanjan"},
        "workflow_status": "completed",
        "variables": {"ip_addr": "10.0.0.1"},
        "execution_results": {1: "ping success"},
        "audit_log": ["[Execution Step 1] ping host"]
    }
    fallback = _build_rich_fallback_summary(state, is_escalated=False)
    assert fallback.resolution_type == "FULLY_RESOLVED"
    assert "Executive Summary" in fallback.internal_ticket_summary
    assert "Diagnostic Findings" in fallback.internal_ticket_summary
    assert "Actions Taken" in fallback.internal_ticket_summary
    assert "Discovered Variables" in fallback.internal_ticket_summary
    assert "ip_addr" in fallback.internal_ticket_summary


def test_summarization_agent_node():
    state = {
        "intent": "Network Sop",
        "sop": {"sop_id": "SOP-NET-001"},
        "entities": {"hostname": "Prabanjan", "employee_name": "Semmozhi"},
        "workflow_status": "completed",
        "execution_results": {1: "IPv4 Address: 192.168.1.15"},
        "audit_log": ["[Execution Result Step 1] Result: SUCCESS."]
    }
    cmd = summarization_agent(state)
    assert cmd.goto == "__end__"
    assert "customer_ticket_reply" in cmd.update
    assert "internal_ticket_summary" in cmd.update
    assert "summarization_details" in cmd.update
    assert cmd.update["summarization_details"]["resolution_type"] in ["FULLY_RESOLVED", "ESCALATED_L2", "MANUAL_INTERVENTION_REQUIRED"]
