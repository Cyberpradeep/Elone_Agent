"""CLI Subprocess and Remote Command execution runner for Execution Agent."""

from typing import Tuple, Dict, Any
from execution_tools import resolve_template_variables, resolve_step_placeholders, run_remote_command


def execute_command_step(
    target_step: Dict[str, Any],
    step_num: int,
    len_steps: int,
    entities: Dict[str, Any],
    variables: Dict[str, Any]
) -> Tuple[str, str, int, str]:
    """Executes a CLI command step on local or remote hosts via WinRM / PowerShell / CMD.

    Returns: (stdout, stderr, exit_code, executed_command_label)
    """
    resolved_step = resolve_step_placeholders(target_step, entities, variables)
    command = resolved_step.get("command", "")
    hostname = entities.get("hostname", "localhost")

    print(f"\n--------------------------------------------------")
    print(f"--- [REMOTE COMMAND RUNNER - STEP {step_num}/{len_steps}] ---")
    print(f"  Description: {target_step.get('sop_step_description')}")
    print(f"  Command: {command}")
    print(f"  Host: {hostname}")
    print(f"--------------------------------------------------")

    target_shell = target_step.get("shell") or "powershell"

    exec_result = run_remote_command(
        hostname=hostname,
        command=command,
        shell=target_shell,
        username=entities.get("username"),
        password=entities.get("password"),
        timeout_seconds=target_step.get("timeout_seconds", 90) or 90,
        elevated=target_step.get("elevated", False),
    )
    stdout = exec_result.get("stdout", "")
    stderr = exec_result.get("stderr", "")
    exit_code = exec_result.get("exit_code", 0)

    # Fallback Command Execution Interception
    fallback_cmd = target_step.get("fallback_command")
    if exit_code != 0 and fallback_cmd:
        fallback_resolved = resolve_template_variables(str(fallback_cmd), entities, variables)
        print(f"  [Execution Fallback Intercept] Primary command failed (exit code {exit_code}). Executing Fallback Command: '{fallback_resolved}'...")

        fallback_res = run_remote_command(
            hostname=hostname,
            command=fallback_resolved,
            shell=target_step.get("shell", "cmd"),
            username=entities.get("username"),
            password=entities.get("password"),
            timeout_seconds=target_step.get("timeout_seconds", 90) or 90,
            elevated=target_step.get("elevated", False),
        )
        stdout = fallback_res.get("stdout", "")
        stderr = fallback_res.get("stderr", "")
        exit_code = fallback_res.get("exit_code", 0)
        command = f"{command} [Fallback Executed: {fallback_resolved}]"

    return stdout, stderr, exit_code, command
