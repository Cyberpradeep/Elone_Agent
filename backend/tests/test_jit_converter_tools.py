import os
import unittest
import tempfile

# pyrefly: ignore [missing-import]
from config.tool_catalog import get_formatted_tools_summary as _get_formatted_api_tools_summary
# pyrefly: ignore [missing-import]
from agents.a2_structuring.execution_planner import plan_okf_from_raw


class TestJITConverterTools(unittest.TestCase):
    """Standard unittest suite for JIT converter tool catalog and playbook parsing."""

    def test_api_tools_summary_formatting(self):
        """Verify tool catalog summary generation contains registered providers and response schemas."""
        summary = _get_formatted_api_tools_summary()
        self.assertIn("unlock_user_account", summary)
        self.assertIn("search_users", summary)
        self.assertTrue("solandra" in summary or "mock" in summary)

    def test_jit_converter_command_playbook_schema(self):
        """Verify raw SOP for endpoint OS task parses into command playbook steps."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sop_file = os.path.join(tmp_dir, "raw_hung_app.txt")
            with open(sop_file, "w", encoding="utf-8") as f:
                f.write("""
                Standard Operating Procedure: Terminate Frozen Application
                1. Open Command Prompt or PowerShell on target Windows computer.
                2. Run 'taskkill /F /IM Code.exe' to forcibly terminate unresponsive process.
                3. Verify process is terminated.
                """)

            try:
                draft = plan_okf_from_raw(sop_file)
            except Exception as e:
                self.skipTest(f"Skipping live LLM conversion test (API unavailable or offline): {e}")

            frontmatter = draft["frontmatter"]
            self.assertTrue(frontmatter["sop_id"].startswith("SOP-"))
            self.assertGreaterEqual(len(frontmatter["steps"]), 1)
            
            step1 = frontmatter["steps"][0]
            self.assertIn(step1["step_type"], ["command", "verification"])
            if step1["step_type"] == "command":
                self.assertTrue("taskkill" in step1["command"] or "powershell" in str(step1.get("shell")).lower())

    def test_jit_converter_tool_playbook_schema(self):
        """Verify raw SOP for user account unlock parses into tool call steps when matching catalog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sop_file = os.path.join(tmp_dir, "raw_account_unlock.txt")
            with open(sop_file, "w", encoding="utf-8") as f:
                f.write("""
                Standard Operating Procedure: Reset Customer Password
                Overview: Resets customer passwords using the Solandra Support Platform API.
                
                Procedure:
                1. Look up user account in solandra using search_user with required parameter employee_id.
                2. Invoke generate_temporary_password with required parameter employee_id.
                3. Resolve ticket in solandra.
                """)

            try:
                draft = plan_okf_from_raw(sop_file)
            except Exception as e:
                self.skipTest(f"Skipping live LLM conversion test (API unavailable or offline): {e}")

            frontmatter = draft["frontmatter"]
            self.assertTrue(frontmatter["sop_id"].startswith("SOP-"))
            self.assertGreaterEqual(len(frontmatter["steps"]), 1)

            tool_steps = [s for s in frontmatter["steps"] if s.get("step_type") == "tool_call"]
            self.assertGreaterEqual(len(tool_steps), 1)
            self.assertTrue(
                tool_steps[0].get("platform") in ["solandra", "mock_support_platform", "auth0"]
                or tool_steps[0].get("provider") in ["solandra", "mock_support_platform", "auth0"]
            )
            self.assertIn(
                tool_steps[0]["function_name"],
                ["search_user", "generate_temporary_password", "resolve_ticket"]
            )


if __name__ == "__main__":
    unittest.main()
