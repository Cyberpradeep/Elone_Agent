"""Fix H4: Full Command and Argument AST Allowlist Guard.

Inspects the entire command string, arguments, flags, and targets rather than
just the initial executable token, preventing privilege escalation and allowlist bypasses.
"""

import re
import shlex
from typing import List, Optional, Set, Tuple

# Protected core system binaries and services that must NEVER be terminated or altered
PROTECTED_SYSTEM_TARGETS: Set[str] = {
    "csrss.exe",
    "lsass.exe",
    "smss.exe",
    "svchost.exe",
    "services.exe",
    "wininit.exe",
    "winlogon.exe",
    "system",
    "init",
    "systemd",
}

# High-risk argument patterns that indicate exploitation attempts
DISALLOWED_ARGUMENT_PATTERNS: List[Tuple[str, str]] = [
    (r"(?:powershell|pwsh).*(?:-enc|-encodedcommand)\s+[A-Za-z0-9+/=]{10,}", "Encoded PowerShell payload execution"),
    (r"(?:invoke-expression|iex)\s*[\(\$]", "Arbitrary script evaluation via Invoke-Expression / iex"),
    (r"certutil(?:\.exe)?\s+-(?:urlcache|decode|decodehex)", "Certutil binary download/decode exploitation"),
    (r"bitsadmin(?:\.exe)?\s+/transfer", "Bitsadmin background downloader"),
    (r"net\s+user\s+[^/\s]+\s+[^/\s]+\s+/add", "Unauthorized local user creation (net user /add)"),
    (r"net\s+localgroup\s+administrators\s+[^/\s]+\s+/add", "Privilege escalation to local administrator"),
    (r"(?:curl|wget)\s+.*https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "Outbound request to raw public IP address"),
    (r"curl\s+-[dF]\s+[@\$]", "Exfiltration of local file or environment variable via curl"),
    (r"rm\s+-rf\s+/(?:$|\s)", "Root filesystem destructive command (rm -rf /)"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", "Fork bomb denial-of-service payload"),
]

# Prohibited shell operators that indicate unapproved command chaining or redirection
CHAINING_OPERATORS = ["&&", "||", ";", "|", "`", "$(", ">", "<"]


class CommandSecurityViolation(Exception):
    """Raised when a command violates full AST argument security policy."""

    pass


def validate_command_and_arguments(
    command_str: str,
    allowed_binaries: Optional[Set[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Inspects the complete command string, flags, and targets against security guardrails.

    Returns (is_valid, error_reason).
    """
    if not command_str or not command_str.strip():
        return False, "Command cannot be empty"

    cmd = command_str.strip()

    # 1. Check for unauthorized shell chaining and redirection first
    for op in CHAINING_OPERATORS:
        if op in cmd:
            return False, f"Unauthorized shell chaining operator '{op}' detected in command arguments"

    # 2. Check against high-risk regex exploitation patterns
    for pattern, description in DISALLOWED_ARGUMENT_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False, f"Prohibited exploit pattern detected: {description}"

    # 3. Tokenize command into binary and arguments
    try:
        # Use posix=False on Windows style commands to keep backslashes intact
        tokens = shlex.split(cmd, posix=False)
    except Exception as e:
        return False, f"Failed to parse command into valid tokens: {e}"

    if not tokens:
        return False, "Command resolved to empty token list"

    binary_token = tokens[0].lower().rstrip(".exe")
    args = [t.lower() for t in tokens[1:]]

    # 4. Check if the binary is in the allowlist (if provided)
    if allowed_binaries:
        clean_allowed = {b.lower().rstrip(".exe") for b in allowed_binaries}
        if binary_token not in clean_allowed:
            return False, f"Binary '{tokens[0]}' is not in the allowed binaries catalog"

    # 5. Check for termination of protected OS targets
    if binary_token in {"taskkill", "kill", "pkill"}:
        for arg in args:
            clean_arg = arg.strip('"/').lower()
            if clean_arg in PROTECTED_SYSTEM_TARGETS:
                return False, f"Action targeting protected system process '{arg}' is strictly forbidden"

    return True, None


def validate_command_or_raise(
    command_str: str,
    allowed_binaries: Optional[Set[str]] = None,
) -> None:
    """Validate command and arguments, raising CommandSecurityViolation if invalid."""
    is_valid, reason = validate_command_and_arguments(command_str, allowed_binaries)
    if not is_valid:
        raise CommandSecurityViolation(f"H4_COMMAND_GUARD_VIOLATION: {reason}")
