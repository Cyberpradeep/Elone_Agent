import os
import datetime
from typing import Any
from pydantic import BaseModel, Field, ValidationError

from okf_engine.loader import load_okf_concept


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.getenv("ELONE_KB_DIR", os.path.join(BASE_DIR, "knowledge_base"))
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
HOSTS_DIR = os.path.join(PATTERNS_DIR, "hosts")
LOGS_DIR = os.path.join(KB_DIR, "logs")
MASTER_LOG_PATH = os.path.join(KB_DIR, "log.md")


class ReflectionRule(BaseModel):
    error_signature: str = Field(description="Substrings or patterns in stdout/stderr identifying the error")
    root_cause: str = Field(description="Underlying technical cause")
    recovery_action: str = Field(description="Specific fix or command adjustment to apply")
    target_host: str = Field(default="All Hosts", description="Host/Environment restriction")


def append_reflection_rule(sop_id: str, rule_dict: dict, category: str = "other") -> bool:
    """Validates with Pydantic, deduplicates, and appends a reflection rule row to patterns/<category>/rules_<SOP_ID>.md."""
    try:
        rule = ReflectionRule(**rule_dict)
    except ValidationError as ve:
        print(f"[Memory Logger Error] Reflection rule validation failed: {ve}")
        return False

    clean_id = sop_id.replace(" ", "_").replace("-", "_")
    cat_dir = os.path.join(PATTERNS_DIR, category.lower())
    os.makedirs(cat_dir, exist_ok=True)
    rulebook_path = os.path.join(cat_dir, f"rules_{clean_id}.md")

    existing_content = ""
    if os.path.exists(rulebook_path):
        with open(rulebook_path, "r", encoding="utf-8") as f:
            existing_content = f.read()

    if rule.error_signature.lower() in existing_content.lower():
        print(f"[Memory Logger Skip] Rule for '{rule.error_signature}' already exists in rulebook.")
        return False

    if not existing_content:
        header = f"""---
type: Reflection Rulebook
sop_id: {sop_id}
category: {category}
updated_at: {datetime.datetime.now().isoformat()}
---

# {sop_id} Reflection Rules & Learned Recovery Patterns

| Error Signature | Root Cause | Verified Recovery Fix | Target Host |
| :--- | :--- | :--- | :--- |
"""
        existing_content = header

    new_row = f"| `{rule.error_signature}` | {rule.root_cause} | {rule.recovery_action} | {rule.target_host} |\n"
    updated_content = existing_content.strip() + "\n" + new_row

    with open(rulebook_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"[SUCCESS] Appended new reflection rule to {rulebook_path}")

    _log_pattern_discovery(sop_id, rule.error_signature, f"{category}/rules_{clean_id}.md")
    return True


def write_episodic_log(ticket_id: Any, sop_id: str, hostname: str, status: str, user_input: str, trajectory: list[str], category: str = "other") -> str:
    """Writes raw episodic execution trace for a ticket run to patterns/logs/<YYYY-MM>/<category>/ticket_<ID>.md."""
    now = datetime.datetime.now()
    month_folder = now.strftime("%Y-%m")
    
    target_dir = os.path.join(PATTERNS_DIR, "logs", month_folder, category.lower())
    os.makedirs(target_dir, exist_ok=True)
    
    log_path = os.path.join(target_dir, f"ticket_{ticket_id}.md")
    trajectory_md = "\n".join([f"- {item}" for item in trajectory])

    content = f"""---
type: Execution Memory
ticket_id: {ticket_id}
sop_id: {sop_id}
category: {category}
hostname: {hostname}
status: {status}
timestamp: {now.isoformat()}
---

# Execution Trace: Ticket #{ticket_id}

## Raw User Input
{user_input}

## Step-by-Step Trajectory
{trajectory_md}

## Resolution Status
`{status}`
"""

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[Memory Logger] Episodic execution trace saved to: {log_path}")
    return log_path


def update_device_profile(hostname: str, target_os: str, quirk_description: str) -> str:
    """Appends or updates learned machine-specific quirks for a target hostname in patterns/hosts/<hostname>.md."""
    if not hostname or hostname in ["(none)", "(unknown)"]:
        return ""

    os.makedirs(HOSTS_DIR, exist_ok=True)
    host_path = os.path.join(HOSTS_DIR, f"{hostname}.md")
    now_str = datetime.datetime.now().isoformat()

    existing_content = ""
    if os.path.exists(host_path):
        with open(host_path, "r", encoding="utf-8") as f:
            existing_content = f.read()

    if quirk_description.lower() in existing_content.lower():
        return host_path

    if not existing_content:
        header = f"""---
type: Device Memory
hostname: {hostname}
target_os: {target_os}
updated_at: {now_str}
---

# Device Profile: {hostname}

## Quirks & Learned Rules
"""
        existing_content = header

    new_quirk = f"- {quirk_description} (Learned: {now_str[:10]})\n"
    updated_content = existing_content.strip() + "\n" + new_quirk

    with open(host_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"[Memory Logger] Device profile updated for host '{hostname}': {host_path}")
    return host_path


def _log_pattern_discovery(sop_id: str, error_sig: str, rel_path: str):
    """Appends pattern discovery event to weekly rotated audit log knowledge_base/logs/<YYYY-WWW>.md."""
    now = datetime.datetime.now()
    week_str = now.strftime("%Y-W%U")
    os.makedirs(LOGS_DIR, exist_ok=True)
    weekly_log_path = os.path.join(LOGS_DIR, f"{week_str}.md")

    timestamp_str = now.strftime("%Y-%m-%d %H:%M")
    log_entry = f"- **{timestamp_str}**: Discovered error rule `{error_sig}` -> `patterns/{rel_path}` ({sop_id}).\n"

    if not os.path.exists(weekly_log_path):
        header = f"# System Audit Log: Week {now.strftime('%U')} ({now.year})\n\n## 🧠 New Pattern Discovery Events\n"
        content = header + log_entry
    else:
        with open(weekly_log_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "## 🧠 New Pattern Discovery Events" in content:
            content = content.replace("## 🧠 New Pattern Discovery Events\n", f"## 🧠 New Pattern Discovery Events\n{log_entry}")
        else:
            content += f"\n## 🧠 New Pattern Discovery Events\n{log_entry}"

    with open(weekly_log_path, "w", encoding="utf-8") as f:
        f.write(content)
