"""
Agent A2: OKF Playbook Builder
==============================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.2 & 17)
Renders OKF Playbook body, stamps HMAC-SHA256, writes .md to knowledge_base/sops/,
and initializes Reflection Rulebooks in knowledge_base/patterns/.
"""

import os
import json
import copy
import yaml
import datetime
import frontmatter
from typing import Dict, Any, Optional

from utils.security import sanitize_slug, compute_playbook_hmac
from agents.a2_structuring.canonical_builder import (
    build_canonical_sop_from_draft,
    write_canonical_sop_json,
)
try:
    from utils.pipeline_logger import log_info, log_warning
except ImportError:
    from backend.utils.pipeline_logger import log_info, log_warning

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.getenv("ELONE_KB_DIR")
if not KB_DIR or not os.path.exists(KB_DIR):
    root_kb = os.path.abspath(os.path.join(BASE_DIR, "..", "knowledge_base"))
    if os.path.exists(root_kb):
        KB_DIR = root_kb
    elif os.path.exists(os.path.join(BASE_DIR, "knowledge_base")):
        KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
    else:
        KB_DIR = root_kb
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
LOGS_DIR = os.path.join(KB_DIR, "logs")
INDEX_PATH = os.path.join(SOPS_DIR, "index.md")


def write_okf_playbook(draft: Dict[str, Any], raw_filename: str = "(reviewed draft)") -> str:
    """Phase 2 (commits to disk): render the OKF body, save the playbook, then
    initialize its rulebook and refresh the catalogs and weekly audit log.
    """
    frontmatter_dict = draft["frontmatter"]
    raw_category = (frontmatter_dict.get("category") or "other").lower().strip()
    category = sanitize_slug(raw_category).lower()
    sop_id = sanitize_slug(frontmatter_dict.get("sop_id") or "SOP-DYN-001")
    frontmatter_dict["category"] = category
    frontmatter_dict["sop_id"] = sop_id
    title = frontmatter_dict["title"]

    steps = frontmatter_dict.get("steps") or []

    # Auto-populate top-level platform if omitted
    if not frontmatter_dict.get("platform"):
        for s in steps:
            if s.get("platform"):
                frontmatter_dict["platform"] = s.get("platform")
                break
        if not frontmatter_dict.get("platform"):
            frontmatter_dict["platform"] = "system"

    # Ensure platform is in trigger_words for fast execution agent lookup
    trigger_words = frontmatter_dict.get("trigger_words") or []
    plat_name = frontmatter_dict.get("platform")
    if plat_name and plat_name != "system" and plat_name.lower() not in [t.lower() for t in trigger_words]:
        trigger_words.insert(0, plat_name)
        frontmatter_dict["trigger_words"] = trigger_words

    # Strip internal LLM step_reasoning from saved YAML frontmatter and markdown body
    clean_frontmatter = copy.deepcopy(frontmatter_dict)
    for s in clean_frontmatter.get("steps", []):
        s.pop("step_reasoning", None)

    # Cryptographic Playbook Integrity Stamp (HMAC-SHA256 v2 Canonical Frontmatter)
    clean_frontmatter["integrity_version"] = "v2"
    clean_frontmatter["integrity_hmac_sha256"] = compute_playbook_hmac(clean_frontmatter)

    yaml_header = yaml.dump(clean_frontmatter, sort_keys=False)
    description = frontmatter_dict.get("description", "")
    markdown_body = f"# {title} Playbook\n\n## Overview\n{description}\n\n"

    markdown_body += "## Execution Steps\n"
    for s in steps:
        if s.get("step_type") == "tool_call":
            platform_prefix = f"Platform: `{s.get('platform')}` | " if s.get("platform") else ""
            tool_name = f"{s.get('platform')}.{s.get('function_name')}"
            inputs_str = json.dumps(s.get("comm_inputs") or {})
            markdown_body += f"- **Step {s.get('step_number')}**: {s.get('sop_step_description')} [{platform_prefix}Tool Call: `{tool_name}({inputs_str})`]\n"
        else:
            cmd = s.get("command") or "(none)"
            fb_cmd = f" [Fallback: `{s.get('fallback_command')}`]" if s.get("fallback_command") else ""
            markdown_body += f"- **Step {s.get('step_number')}**: {s.get('sop_step_description')} (`{cmd}`){fb_cmd}\n"

    okf_content = f"---\n{yaml_header}---\n\n{markdown_body}"

    # 3. Save OKF File to knowledge_base/sops/<category>/<sop_id>.md
    category_dir = os.path.join(SOPS_DIR, category)
    os.makedirs(category_dir, exist_ok=True)
    okf_file_path = os.path.join(category_dir, f"{sop_id}.md")

    with open(okf_file_path, "w", encoding="utf-8") as f:
        f.write(okf_content)

    log_info("OKF Builder", f"JIT OKF Playbook saved to: {os.path.basename(okf_file_path)}")

    # 4. Auto-initialize Reflection Rulebook knowledge_base/patterns/<category>/rules_<SOP_ID>.md
    _initialize_reflection_rulebook(sop_id, title, category)

    # 5. Update Catalogs & Weekly Rotated System Log
    rel_path = f"{category}/{sop_id}.md"
    _update_sops_catalog_indexes()
    _log_okf_creation(sop_id, title, raw_filename, rel_path)

    # 6. Dual Export: Save Canonical SOP JSON 1.0 (Section 16) alongside OKF Playbook
    try:
        canonical_data = build_canonical_sop_from_draft(draft, raw_text=draft.get("raw_text", ""))
        write_canonical_sop_json(canonical_data, category=category)
    except Exception as e:
        log_warning("OKF Builder", f"Dual export canonical JSON generation failed: {e}")

    return okf_file_path


def _initialize_reflection_rulebook(sop_id: str, title: str, category: str):
    """Auto-initializes rules_<SOP_ID>.md inside knowledge_base/patterns/<category>/."""
    pattern_cat_dir = os.path.join(PATTERNS_DIR, category)
    os.makedirs(pattern_cat_dir, exist_ok=True)
    rulebook_path = os.path.join(pattern_cat_dir, f"rules_{sop_id}.md")

    if not os.path.exists(rulebook_path):
        content = f"""---
sop_id: {sop_id}
title: {title} Reflection Rulebook
category: {category}
type: ReflectionRulebook
---

# {title} Reflection Rulebook

| Rule ID | Error Signature | Root Cause | Verified Recovery Fix | Target Host |
| :--- | :--- | :--- | :--- | :--- |
"""
        with open(rulebook_path, "w", encoding="utf-8") as f:
            f.write(content)
        log_info("Memory Logger", f"Auto-initialized Reflection Rulebook: {os.path.basename(rulebook_path)}")


def _update_sops_catalog_indexes():
    """Generates sops/<category>/index.md for each category and updates master sops/index.md."""
    if not os.path.exists(SOPS_DIR):
        return

    master_entries = []

    for cat_name in sorted(os.listdir(SOPS_DIR)):
        cat_path = os.path.join(SOPS_DIR, cat_name)
        if os.path.isdir(cat_path):
            cat_entries = []
            for filename in sorted(os.listdir(cat_path)):
                if filename.endswith(".md") and filename != "index.md":
                    filepath = os.path.join(cat_path, filename)
                    try:
                        post = frontmatter.load(filepath)
                        title = post.metadata.get("title", filename)
                        cat = post.metadata.get("category", cat_name)
                        platform = post.metadata.get("platform", "system")
                        desc = post.metadata.get("description", "Playbook procedure.")
                        triggers = post.metadata.get("trigger_words", [])
                        triggers_str = ", ".join(triggers) if isinstance(triggers, list) else str(triggers)
                        rel_path = f"{cat_name}/{filename}"
                        
                        entry = f"- [{title}](./{rel_path}) | Platform: `{platform}` | Category: `{cat}` | Triggers: `{triggers_str}` | {desc}"
                        cat_entries.append(f"- [{title}](./{filename}) | Platform: `{platform}` | Triggers: `{triggers_str}` | {desc}")
                        master_entries.append(entry)
                    except Exception as e:
                        log_warning("OKF Catalog", f"Failed reading {filename}: {e}")

            if cat_entries:
                cat_index_content = f"# {cat_name.capitalize()} Playbooks Catalog\n\n" + "\n".join(cat_entries) + "\n"
                with open(os.path.join(cat_path, "index.md"), "w", encoding="utf-8") as f:
                    f.write(cat_index_content)

    master_content = "# Active Playbooks Catalog\n\n" + "\n".join(master_entries) + "\n"
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(master_content)


def _log_okf_creation(sop_id: str, title: str, raw_filename: str, rel_path: str):
    """Appends creation event to weekly rotated audit log knowledge_base/logs/<YYYY-WWW>.md."""
    now = datetime.datetime.now()
    week_str = now.strftime("%Y-W%U")
    os.makedirs(LOGS_DIR, exist_ok=True)
    weekly_log_path = os.path.join(LOGS_DIR, f"{week_str}.md")

    log_entry = f"- [{now.strftime('%Y-%m-%d %H:%M')}] **Created Playbook `{sop_id}`**: '{title}' from raw file `{raw_filename}` (Path: `{rel_path}`)\n"

    if not os.path.exists(weekly_log_path):
        header = f"# System Audit Log - Week {week_str}\n\n## Creation Events\n"
        with open(weekly_log_path, "w", encoding="utf-8") as f:
            f.write(header + log_entry)
    else:
        with open(weekly_log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
