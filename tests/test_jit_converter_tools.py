import os
import pytest
from agents.jit_converter.node import _get_formatted_api_tools_summary, plan_okf_from_raw, write_okf_playbook
from shared.tool_catalog import TOOL_CATALOG, PROVIDERS


def test_api_tools_summary_formatting():
    """Verify tool catalog summary generation contains registered providers and response schemas."""
    summary = _get_formatted_api_tools_summary()
    assert "mock_support_platform" in summary
    assert "unlock_user_account" in summary
    assert "search_users" in summary
    assert "Response Schema" in summary


def test_jit_converter_command_playbook_schema(tmp_path):
    """Verify raw SOP for endpoint OS task parses into command playbook steps."""
    sop_file = tmp_path / "raw_hung_app.txt"
    sop_file.write_text("""
    Standard Operating Procedure: Terminate Frozen Application
    1. Open Command Prompt or PowerShell on target Windows computer.
    2. Run 'taskkill /F /IM Code.exe' to forcibly terminate unresponsive process.
    3. Verify process is terminated.
    """, encoding="utf-8")

    draft = plan_okf_from_raw(str(sop_file))
    frontmatter = draft["frontmatter"]

    assert frontmatter["sop_id"].startswith("SOP-")
    assert len(frontmatter["steps"]) >= 1
    
    step1 = frontmatter["steps"][0]
    assert step1["step_type"] in ["command", "verification"]
    if step1["step_type"] == "command":
        assert "taskkill" in step1["command"] or "powershell" in str(step1.get("shell")).lower()


def test_jit_converter_tool_playbook_schema(tmp_path):
    """Verify raw SOP for user account unlock parses into tool call steps when matching catalog."""
    sop_file = tmp_path / "raw_account_unlock.txt"
    sop_file.write_text("""
    Standard Operating Procedure: Unlock Customer Account
    Overview: Unlocks locked user accounts using the Mock Support Platform REST API.
    
    Procedure:
    1. Look up user account in mock_support_platform using search_users by customer email.
    2. Invoke unlock_user_account with required parameter user_id.
    3. Verify response status is unlocked.
    """, encoding="utf-8")

    draft = plan_okf_from_raw(str(sop_file))
    frontmatter = draft["frontmatter"]

    assert frontmatter["sop_id"].startswith("SOP-")
    assert len(frontmatter["steps"]) >= 1

    tool_steps = [s for s in frontmatter["steps"] if s.get("step_type") == "tool_call"]
    assert len(tool_steps) >= 1
    assert tool_steps[0]["provider"] in ["mock_support_platform", "auth0"]
    assert tool_steps[0]["function_name"] in ["unlock_user_account", "search_users", "search_user"]
