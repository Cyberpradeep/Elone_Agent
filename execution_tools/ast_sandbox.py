"""Enterprise AST Command Sandbox & Allowlist Filter for Execution Engine."""

import re
from typing import List, Dict, Any, Tuple, Optional

# High-Risk Security / Prompt Injection Command Patterns
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
    # Registry & System Inspection
    "reg", "reg.exe", "query", "find", "findstr",
    # PowerShell Core Utilities, Pipelines & Filesystem
    "where-object", "select-object", "foreach-object", "measure-object",
    "group-object", "sort-object", "out-null", "out-string", "out-file",
    "write-output", "write-host", "write-verbose", "write-warning",
    "get-date", "get-random", "join-path", "split-path", "resolve-path",
    "test-path", "get-item", "get-childitem", "get-itemproperty", "get-content",
    "set-content", "add-content", "clear-content", "new-item", "remove-item",
    "copy-item", "move-item", "clear-item", "set-item", "get-variable", "set-variable",
    # Text Processing & Utilities
    "echo", "grep", "awk", "sed", "cat", "head", "tail",
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
    """Enforces enterprise command allowlist with fail-closed security."""
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
                    "pattern": "malicious_command_pattern",
                    "description": threat_desc,
                })
                break
    return threats

