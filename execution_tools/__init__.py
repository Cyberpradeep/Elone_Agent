"""Execution tools package for remote command execution, communication, and variable resolution."""

from .variable_resolver import resolve_template_variables, resolve_step_placeholders
from .winrm_executor import run_remote_command as run_winrm_command
from .ssh_executor import run_remote_ssh_command, run_remote_ssh_command as run_remote_command
from .comm_executor import execute_comm_tool

__all__ = [
    "resolve_template_variables",
    "resolve_step_placeholders",
    "run_remote_command",
    "run_remote_ssh_command",
    "run_winrm_command",
    "execute_comm_tool",
]
