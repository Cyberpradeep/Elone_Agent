"""
Agent A3: AST Command Sandbox
==============================
Gate 6 Layer 1: Deterministic AST & Blacklist Scan (<1ms).
Bans LOLBins (certutil, bitsadmin, mshta), encoded PowerShell, and prompt injection breakouts.
"""

import re
from typing import List, Dict, Any, Tuple
from agents.a4_verification.plan_validator import (
    MALICIOUS_COMMAND_PATTERNS,
)


def scan_commands_for_ast_threats(commands: List[str]) -> List[Dict[str, str]]:
    """Scans command strings against deterministic LOLBin and injection patterns."""
    threats = []
    for cmd in commands:
        if not cmd:
            continue
        for pattern, threat_desc in MALICIOUS_COMMAND_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                threats.append({
                    "command": cmd,
                    "pattern": pattern,
                    "description": threat_desc,
                })
    return threats


__all__ = [
    "scan_commands_for_ast_threats",
    "validate_command_sandbox",
    "MALICIOUS_COMMAND_PATTERNS",
]

validate_command_sandbox = scan_commands_for_ast_threats
