"""CLI Subprocess and Remote Command execution runner for Execution Agent."""

from typing import Tuple, Dict, Any
from execution_tools import (
    resolve_template_variables,
    resolve_step_placeholders,
    run_remote_command,
    scan_commands_for_ast_threats,
)


def execute_command_step(
    target_step: Dict[str, Any],
    step_num: int,
    len_steps: int,
    entities: Dict[str, Any],
    variables: Dict[str, Any]
) -> Tuple[str, str, int, str]:
    """Executes a CLI command step on local or remote hosts via WinRM / PowerShell / CMD.

    Enforces pre-execution AST allowlist and LOLBin injection sandboxing.
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

    # Security AST Sandbox & Threat Pattern Check
    threats = scan_commands_for_ast_threats([command])
    if threats:
        threat_desc = threats[0].get("description", "Blocked by security sandbox")
        err_msg = f"[Security Sandbox Violation]: Command '{command}' was blocked: {threat_desc}"
        print(f"  {err_msg}")
        return "", err_msg, 126, f"{command} [SECURITY BLOCKED]"

    target_shell = target_step.get("shell") or "powershell"
    target_os = entities.get("target_os") or target_step.get("target_os") or "windows"

    exec_result = run_remote_command(
        hostname=hostname,
        command=command,
        shell=target_shell,
        target_os=target_os,
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

        fallback_threats = scan_commands_for_ast_threats([fallback_resolved])
        if fallback_threats:
            threat_desc = fallback_threats[0].get("description", "Blocked by security sandbox")
            err_msg = f"[Security Sandbox Violation]: Fallback command '{fallback_resolved}' was blocked: {threat_desc}"
            print(f"  {err_msg}")
            return stdout, f"{stderr}\n{err_msg}", 126, f"{command} [Fallback Security Blocked]"

        fallback_res = run_remote_command(
            hostname=hostname,
            command=fallback_resolved,
            shell=target_step.get("shell", "cmd"),
            target_os=target_os,
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
