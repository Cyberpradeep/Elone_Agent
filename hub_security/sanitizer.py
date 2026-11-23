"""Fix M3: Prompt Delimiter Sanitization & Boundary Guard.

Escapes all '<' and '>' characters and wraps untrusted user, ticket, or tool
payloads in strict, non-executable data boundaries to prevent prompt injection.
"""

import html
import re
from typing import Dict, Any


def escape_prompt_delimiters(text: str) -> str:
    """Escapes XML and HTML delimiter characters '<' and '>' from input strings.

    Prevents prompt injection payloads from spoofing system prompt tags
    (e.g., <system>, <instructions>, <admin_override>).
    """
    if not text:
        return ""
    # Explicit replacement of angle brackets
    sanitized = text.replace("<", "&lt;").replace(">", "&gt;")
    return sanitized


def wrap_untrusted_data(boundary_label: str, text: str) -> str:
    """Wraps text within a hardened, structured non-executable data fence."""
    escaped_body = escape_prompt_delimiters(text)
    clean_label = re.sub(r"[^A-Z0-9_-]", "_", boundary_label.upper())

    return (
        f"\n--- BEGIN UNTRUSTED DATA ({clean_label}) ---\n"
        f"{escaped_body}\n"
        f"--- END UNTRUSTED DATA ({clean_label}) ---\n"
    )


def sanitize_incoming_ticket(ticket_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitizes string fields in ticket and incident payloads."""
    sanitized: Dict[str, Any] = {}
    for key, value in ticket_payload.items():
        if isinstance(value, str):
            sanitized[key] = escape_prompt_delimiters(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_incoming_ticket(value)
        elif isinstance(value, list):
            sanitized[key] = [
                escape_prompt_delimiters(v) if isinstance(v, str) else v for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized

