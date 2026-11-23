"""Hardened Prompt Injection Detection, Secret Scrubbing, and Fencing Guard.

Protects LLM decision plane from:
- Indirect prompt injection (system override, jailbreak markers, instruction delimiters).
- Delimiter spoofing (<script>, <system>, <untrusted_data>).
- Credential leakage (redacts passwords, authorization tokens, API keys).
"""

import html
import re
from typing import Dict, List, Tuple


INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions",
    r"system\s+(?:override|prompt)",
    r"bypass\s+(?:security|policy|guardrails)",
    r"<script\b[^>]*>",
    r"--- (?:BEGIN|END) SYSTEM ---",
    r"--- (?:BEGIN|END) UNTRUSTED DATA ---",
    r"\bexec\s*\(|\beval\s*\(",
    r"\bformat\s+[a-z]:|\brm\s+-rf|\bdel\s+/[fqs]",
]

COMPILED_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

SECRET_PATTERNS = [
    (r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?", r"password=[REDACTED]"),
    (r"(?i)(?:bearer\s+)[a-zA-Z0-9_\-\.]{15,}", "Bearer [REDACTED_TOKEN]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?", r"api_key=[REDACTED]"),
]


def detect_prompt_injection(text: str) -> Tuple[bool, List[str]]:
    """Scan input text against authoritative prompt injection regex signatures."""
    if not text:
        return False, []

    matched_patterns = []
    for pattern in COMPILED_INJECTION_RE:
        if pattern.search(text):
            matched_patterns.append(pattern.pattern)

    return len(matched_patterns) > 0, matched_patterns


def scrub_sensitive_secrets(text: str) -> str:
    """Redact passwords, bearer tokens, and API credentials from raw text."""
    if not text:
        return ""

    scrubbed = text
    for pattern, replacement in SECRET_PATTERNS:
        scrubbed = re.sub(pattern, replacement, scrubbed)

    return scrubbed


def escape_delimiters(text: str) -> str:
    """Escapes '<' and '>' to prevent XML delimiter breakout."""
    if not text:
        return ""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def sanitize_and_fence_text(text: str, label: str = "TICKET_BODY") -> str:
    """Cleanses secrets, escapes angle brackets, and wraps in hardened XML fence."""
    scrubbed = scrub_sensitive_secrets(text)
    escaped = escape_delimiters(scrubbed)
    clean_label = re.sub(r"[^A-Z0-9_-]", "_", label.upper())

    return (
        f"<untrusted_data boundary=\"{clean_label}\">\n"
        f"{escaped}\n"
        f"</untrusted_data>"
    )
