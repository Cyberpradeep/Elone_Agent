"""Governance Hub Security Hardening Package (PR-04).

Remediates N1 (immutability), H4 (AST command/argument guard),
and M3 (prompt injection delimiter escaping).
"""

from hub_security.immutability import (
    ImmutableSOPError,
    check_sop_immutability,
    validate_semver_progression,
)
from hub_security.command_guard import (
    CommandSecurityViolation,
    validate_command_and_arguments,
    validate_command_or_raise,
    PROTECTED_SYSTEM_TARGETS,
)
from hub_security.sanitizer import (
    escape_prompt_delimiters,
    wrap_untrusted_data,
    sanitize_incoming_ticket,
)

__all__ = [
    "ImmutableSOPError",
    "check_sop_immutability",
    "validate_semver_progression",
    "CommandSecurityViolation",
    "validate_command_and_arguments",
    "validate_command_or_raise",
    "PROTECTED_SYSTEM_TARGETS",
    "escape_prompt_delimiters",
    "wrap_untrusted_data",
    "sanitize_incoming_ticket",
]
