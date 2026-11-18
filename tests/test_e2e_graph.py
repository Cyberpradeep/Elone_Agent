import pytest
from unittest.mock import patch
from graph import graph


def test_end_to_end_graph_execution_flow():
    """End-to-End Workflow Verification:
    Tests ticket intake -> planner -> orchestration -> HITL interrupt -> execution -> result parsing -> summarization.
    """
    thread_id = "test_thread_e2e_001"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "ticket_id": 8801,
        "customer_email": "pradeepnaveen930@gmail.com",
        "category": "software",
        "ticket_raw": "Please unblock VS Code application (Code.exe) for email pradeepnaveen930@gmail.com",
        "entities": {"email": "pradeepnaveen930@gmail.com", "executable": "Code.exe"},
        "workflow_status": "pending",
        "audit_log": []
    }

    # Step 1: Run graph from START until the HITL interrupt before execution_agent
    paused_state = graph.invoke(initial_state, config=config)

    # Verify pause occurred before execution_agent
    snapshot = graph.get_state(config)
    assert "execution_agent" in snapshot.next, f"Expected interrupt before execution_agent, got {snapshot.next}"

    # Verify intermediate state produced by intake and planner
    current_values = snapshot.values
    assert current_values.get("plan_valid") is True
    assert current_values.get("execution_plan") is not None
    assert len(current_values["execution_plan"].get("steps", [])) >= 1
    assert current_values.get("entities", {}).get("hostname") == "DESKTOP-O9HENH2"

    # Step 2: Simulate HITL Approval and mock remote execution to return clean output
    mock_run_result = {
        "command": "tasklist",
        "exit_code": 0,
        "stdout": "Code.exe                      1234 Console                    1     74,320 K",
        "stderr": "",
        "status": "success",
        "execution_method": "winrm",
        "remote": True
    }

    with patch("agents.execution.command_runner.run_remote_command", return_value=mock_run_result):
        # Resume the graph through each HITL approval step until execution finishes
        max_turns = 10
        turns = 0
        final_state = paused_state
        while turns < max_turns:
            snapshot = graph.get_state(config)
            if not snapshot.next or "execution_agent" not in snapshot.next:
                final_state = snapshot.values
                break
            final_state = graph.invoke(None, config=config)
            turns += 1

    # Verify final completion through execution_result and summarization
    assert final_state.get("workflow_status") in ["done", "completed"]
    assert "customer_ticket_reply" in final_state
    assert len(final_state["customer_ticket_reply"]) > 20
    assert "internal_ticket_summary" in final_state
    assert len(final_state["internal_ticket_summary"]) > 50
    assert len(final_state.get("audit_log", [])) > 3
