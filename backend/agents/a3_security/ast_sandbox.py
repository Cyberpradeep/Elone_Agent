"""
Agent A3: AST Command Sandbox
==============================
Gate 6 Layer 1 & Stage 2 Pre-Filter: Deterministic AST & Blacklist Scan (<1ms).
Bans LOLBins (certutil, bitsadmin, mshta), encoded PowerShell, credential dumpers,
and prompt injection breakouts across both raw SOP documents and structured commands.
"""

import ipaddress
import re
from typing import List, Dict, Any
try:
    from agents.a4_verification.plan_validator import MALICIOUS_COMMAND_PATTERNS
except ImportError:
    from backend.agents.a4_verification.plan_validator import MALICIOUS_COMMAND_PATTERNS
try:
    from utils.security import clean_unicode_and_zero_width
except ImportError:
    from backend.utils.security import clean_unicode_and_zero_width


_LINE_PREFIX_RE = re.compile(r"^(?:[>*•\-–]+\s+|\d+[\.\)]\s+|\[[ xX]\]\s+)+")
_RAW_IP_URL_RE = re.compile(r"https?://(\d{1,3}(?:\.\d{1,3}){3})(?=[:/\s\"'\)\]]|$)", re.IGNORECASE)
# Keep short upload/exfil flags (-d, -F, -T) case-sensitive so lowercase `-f` (`curl --fail`) is permitted.
_CURL_UPLOAD_FLAG_RE = re.compile(r"(?:^|\s)(?:-[dFT]\b|--(?:data(?:-[a-zA-Z]+)?|upload-file|form)\b)")
_MIMIKATZ_EXEC_CONTEXT_RE = re.compile(
    r"(?:"
    r"\bmimikatz\.exe\b"
    r"|mimikatz::"
    r"|`[^`\n]*\bmimikatz\b[^`\n]*`"
    r"|^\s*(?:cmd(?:\.exe)?\s*/[ck]\s*)?mimikatz\b"
    r"|[;|&]\s*mimikatz\b"
    r"|\b(?:powershell|pwsh)(?:\.exe)?\b[^\n.;]*\bmimikatz\b"
    r"|\b(?:run|execute|launch|invoke|download|fetch|start|using|via)\s+(?:the\s+|this\s+|a\s+)?mimikatz\b(?!\s+(?:detection|signatures?|alerts?|indicators?|rules?|activity))"
    r"|https?://[^\s]*mimikatz"
    r"|(?:[A-Za-z]:\\|/[^\s]*/)[^\s]*mimikatz"
    r"|\bmimikatz\s+\"[^\n\"]+\""
    r"|\bprivilege::debug\b"
    r")",
    re.IGNORECASE,
)


def _is_raw_sop_false_positive(candidate_text: str, unwrapped_text: str, threat_desc: str) -> bool:
    """Apply narrow precision guards so benign raw SOP documentation does not false-positive."""
    if threat_desc == "Outbound network request to raw public IP":
        # Allow local service healthchecks targeting loopback (e.g. `curl -s -f http://127.0.0.1:8080/health`)
        # unless upload/exfiltration flags or any non-loopback IP appear on the line.
        ips = _RAW_IP_URL_RE.findall(candidate_text)
        if not ips:
            return False
        parsed_ips = []
        for ip_s in ips:
            try:
                parsed_ips.append(ipaddress.ip_address(ip_s))
            except ValueError:
                return False
        if parsed_ips and all(ip.is_loopback for ip in parsed_ips) and not _CURL_UPLOAD_FLAG_RE.search(candidate_text):
            return True
        return False

    if threat_desc == "Credential dumping tool execution":
        # Always flag Invoke-Mimikatz or sekurlsa references anywhere; for bare 'mimikatz',
        # allow defensive SOC/EDR prose (e.g. "if Mimikatz execution is detected") while
        # blocking executable invocations, scripts, paths, flags, and URLs.
        lower = unwrapped_text.lower()
        if "invoke-mimikatz" in lower or "sekurlsa" in lower:
            return False
        return not bool(_MIMIKATZ_EXEC_CONTEXT_RE.search(unwrapped_text))

    return False


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


def scan_raw_sop_for_ast_threats(raw_text: str) -> List[Dict[str, Any]]:
    """Broadly scans raw SOP lines and inline prose for malicious commands at Stage 2.

    Unlike column-0 prefix filtering, this normalizes obfuscated Unicode/zero-width
    characters and unwraps list markers, blockquotes, and markdown backticks on every
    non-empty line before matching against MALICIOUS_COMMAND_PATTERNS.
    """
    if not raw_text:
        return []

    normalized = clean_unicode_and_zero_width(raw_text)
    threats: List[Dict[str, Any]] = []

    for line_num, raw_line in enumerate(normalized.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        unwrapped = _LINE_PREFIX_RE.sub("", stripped).strip()
        unwrapped_no_ticks = unwrapped.replace("`", "")

        candidates = [stripped]
        for cand in (unwrapped, unwrapped_no_ticks):
            if cand and cand not in candidates:
                candidates.append(cand)

        seen_patterns_on_line = set()
        for pattern, threat_desc in MALICIOUS_COMMAND_PATTERNS:
            if pattern in seen_patterns_on_line:
                continue
            for cand in candidates:
                if re.search(pattern, cand, re.IGNORECASE):
                    if _is_raw_sop_false_positive(cand, unwrapped, threat_desc):
                        continue
                    seen_patterns_on_line.add(pattern)
                    threats.append({
                        "line_number": line_num,
                        "command": stripped[:240],
                        "pattern": pattern,
                        "description": threat_desc,
                    })
                    break

    return threats


__all__ = [
    "scan_commands_for_ast_threats",
    "scan_raw_sop_for_ast_threats",
    "validate_command_sandbox",
    "MALICIOUS_COMMAND_PATTERNS",
]

validate_command_sandbox = scan_commands_for_ast_threats
