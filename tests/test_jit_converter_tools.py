# pyrefly: ignore [missing-import]
from elone_sop import (
    get_formatted_tools_summary as _get_formatted_api_tools_summary,
    plan_okf_from_raw,
)


def test_api_tools_summary_formatting():
    """Verify tool catalog summary generation contains registered providers and response schemas."""
    summary = _get_formatted_api_tools_summary()
    assert "unlock_user_account" in summary
    assert "search_users" in summary
    assert "solandra" in summary or "mock" in summary


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
    Standard Operating Procedure: Reset Customer Password
    Overview: Resets customer passwords using the Solandra Support Platform API.
    
    Procedure:
    1. Look up user account in solandra using search_user with required parameter employee_id.
    2. Invoke generate_temporary_password with required parameter employee_id.
    3. Resolve ticket in solandra.
    """, encoding="utf-8")

    draft = plan_okf_from_raw(str(sop_file))
    frontmatter = draft["frontmatter"]

    assert frontmatter["sop_id"].startswith("SOP-")
    assert len(frontmatter["steps"]) >= 1

    tool_steps = [s for s in frontmatter["steps"] if s.get("step_type") == "tool_call"]
    assert len(tool_steps) >= 1
    assert tool_steps[0].get("platform") in ["solandra", "mock_support_platform", "auth0"] or tool_steps[0].get("provider") in ["solandra", "mock_support_platform", "auth0"]
    assert tool_steps[0]["function_name"] in ["search_user", "generate_temporary_password", "resolve_ticket"]
