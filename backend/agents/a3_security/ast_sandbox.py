"""
Agent A3: AST Command Sandbox
==============================
Gate 6 Layer 1 & Stage 2 Pre-Filter: Deterministic AST & Blacklist Scan (<1ms).
Bans LOLBins (certutil, bitsadmin, mshta), encoded PowerShell, credential dumpers,
and prompt injection breakouts across both raw SOP documents and structured commands.
"""

import ipaddress
import re
from typing import List, Dict, Any, Tuple, Optional
# Deterministic High-Risk Security / Prompt Injection Command Patterns
MALICIOUS_COMMAND_PATTERNS = [
    (r"(?:powershell|pwsh).*(?:-enc|-encodedcommand)\s+[A-Za-z0-9+/=]{10,}", "Encoded PowerShell payload execution"),
    (r"(?:invoke-expression|iex)\s*[\(\$]", "Arbitrary script evaluation (Invoke-Expression / IEX)"),
    (r"certutil(?:\.exe)?\s+-(?:urlcache|decode|decodehex)", "Certutil binary download/decode exploitation"),
    (r"bitsadmin(?:\.exe)?\s+/transfer", "Bitsadmin background downloader"),
    (r"net\s+user\s+[^/\s]+\s+[^/\s]+\s+/add", "Unauthorized backdoor local user creation (net user /add)"),
    (r"net\s+localgroup\s+administrators\s+[^/\s]+\s+/add", "Privilege escalation to local administrator"),
    (r"(?:curl|wget)\s+.*https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "Outbound network request to raw public IP"),
    (r"curl\s+-[dF]\s+[@\$]", "Outbound file exfiltration via curl POST/form"),
    (r"(?:chmod\s+777|chown\s+root|useradd|usermod\s+-aG\s+sudo)", "Privilege escalation / insecure file permission alteration"),
    (r"mimikatz|Invoke-Mimikatz|sekurlsa", "Credential dumping tool execution"),
]
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


ALLOWED_COMMAND_ROOTS = {
    # Network & Diagnostics
    "test-connection", "test-netconnection", "ping", "tracert", "traceroute",
    "nslookup", "ipconfig", "ifconfig", "netstat", "netsh", "route", "arp",
    "dig", "host", "curl", "wget", "get-netadapter", "get-netipaddress",
    "get-netipconfiguration", "get-netroute", "get-dnsclientserveraddress",
    "resolve-dnsname",
    # Service & Process Management
    "get-service", "restart-service", "start-service", "stop-service", "set-service",
    "get-process", "stop-process", "start-process", "wait-process",
    "tasklist", "taskkill", "net", "systemctl", "journalctl", "service", "sc",
    # PowerShell Core Utilities, Pipelines & Filesystem
    "where-object", "select-object", "foreach-object", "measure-object",
    "group-object", "sort-object", "out-null", "out-string", "out-file",
    "write-output", "write-host", "write-verbose", "write-warning",
    "get-date", "get-random", "join-path", "split-path", "resolve-path",
    "test-path", "get-item", "get-childitem", "get-itemproperty", "get-content",
    "set-content", "add-content", "clear-content", "new-item", "remove-item",
    "copy-item", "move-item", "clear-item", "set-item", "get-variable", "set-variable",
    # Text Processing & Utilities
    "echo", "findstr", "find", "grep", "awk", "sed", "cat", "head", "tail",
    "wc", "diff", "sort", "uniq",
    # System Info & Directory Queries
    "whoami", "id", "hostname", "uname", "uptime", "systeminfo", "gpresult",
    "gpupdate", "get-aduser", "get-adcomputer", "get-adgroup", "dsquery",
    "get-eventlog", "get-winevent", "get-hotfix", "get-wmiobject", "get-ciminstance",
    # Launchers & Platform Helpers
    "start", "mstsc", "save-profile", "save-rdp-profile", "save-pc-profile",
    "vpn-save", "vpn-connect", "vpn-disconnect", "cisco-anyconnect",
}

WRAPPER_BINARIES = {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "sudo"}


def extract_command_roots(cmd_str: str) -> List[str]:
    """Extracts base executable or cmdlet names from a single or compound command string."""
    clean = re.sub(r'#.*$', '', cmd_str, flags=re.MULTILINE)
    clean = re.sub(r'\b(if|while|foreach)\s*\([^)]*\)\s*\{', ' ', clean)
    clean = clean.replace('{', ' ').replace('}', ' ')
    statements = re.split(r'[\r\n;&|]+', clean)
    roots = []
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt:
            continue
        stmt = re.sub(r'^\$[a-zA-Z0-9_]+\s*=\s*', '', stmt).strip()
        if not stmt:
            continue
        tokens = stmt.split()
        if not tokens:
            continue
        i = 0
        while i < len(tokens) and tokens[i].lower() in WRAPPER_BINARIES:
            i += 1
            while i < len(tokens) and tokens[i].startswith('-'):
                i += 1
            if i < len(tokens) and tokens[i].lower() in ('/c', '/k'):
                i += 1
        if i >= len(tokens):
            candidate = tokens[0]
        else:
            candidate = tokens[i]
        candidate = candidate.strip('\'"`()')
        candidate = re.sub(r'\.(exe|cmd|bat|ps1)$', '', candidate, flags=re.IGNORECASE)
        candidate = candidate.split('\\')[-1].split('/')[-1]
        if candidate and not candidate.startswith('$'):
            roots.append(candidate.lower())
    return roots


def validate_command_against_allowlist(cmd_str: str) -> Tuple[bool, Optional[str]]:
    """Enforces enterprise command allowlist with fail-closed security.

    Verifies that every executable root/cmdlet in a single or chained/piped command
    belongs to ALLOWED_COMMAND_ROOTS.
    """
    if not cmd_str or not cmd_str.strip():
        return False, "Command string is empty."
    roots = extract_command_roots(cmd_str)
    if not roots:
        return False, "Unable to extract valid command binary from step."
    for r in roots:
        if r not in ALLOWED_COMMAND_ROOTS:
            return False, f"Command binary or cmdlet '{r}' is not in the approved enterprise command allowlist."
    return True, None


def scan_commands_for_ast_threats(commands: List[str]) -> List[Dict[str, str]]:
    """Scans command strings against deterministic allowlist and LOLBin injection patterns."""
    threats = []
    for cmd in commands:
        if not cmd:
            continue
        # 1. Allowlist verification (Fail closed on unapproved binary/cmdlet)
        is_allowed, allow_err = validate_command_against_allowlist(cmd)
        if not is_allowed:
            threats.append({
                "command": cmd,
                "pattern": "command_allowlist_violation",
                "description": allow_err or "Command not in approved enterprise allowlist",
            })
            continue

        # 2. Defense-in-depth: scan against high-risk pattern denylist
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
    "validate_command_against_allowlist",
    "extract_command_roots",
    "ALLOWED_COMMAND_ROOTS",
    "MALICIOUS_COMMAND_PATTERNS",
]

validate_command_sandbox = scan_commands_for_ast_threats
