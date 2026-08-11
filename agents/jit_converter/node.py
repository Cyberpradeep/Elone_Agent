import os
import json
import re
import datetime
# pyrefly: ignore [missing-import]
import yaml
# pyrefly: ignore [missing-import]
import frontmatter
from typing import Tuple, Dict, Any, Optional

from shared.llm_config import get_llm
from .document_parser import extract_full_text
from agents.plan_validator.validator import validate_plan_faithfulness_and_linkage


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
LOGS_DIR = os.path.join(KB_DIR, "logs")
INDEX_PATH = os.path.join(SOPS_DIR, "index.md")


def _get_formatted_api_tools_summary() -> str:
    """Returns a human-readable summary of active API tools for the JIT Converter LLM prompt."""
    try:
        from shared.tool_catalog import PROVIDERS
        summary_lines = []
        for p in PROVIDERS:
            for tool in p.get_tool_metadata():
                tool_name = tool.get("tool_name", p.provider_name)
                desc = tool.get("description", "No description provided.")
                summary_lines.append(f"- Provider Name: '{p.provider_name}' | Tool Name: '{tool_name}'")
                summary_lines.append(f"  Description: {desc}")
                summary_lines.append("  Available Functions:")
                for fn in tool.get("functions", []):
                    req_inputs = ", ".join(fn.get("required_inputs", []))
                    fn_desc = fn.get("description", "")
                    summary_lines.append(f"    * {fn['function_name']}({req_inputs}): {fn_desc}")
                    resp_schema = fn.get("response_schema") or fn.get("returns")
                    if resp_schema:
                        summary_lines.append(f"      → Response Schema: {json.dumps(resp_schema)}")
        return "\n".join(summary_lines)
    except Exception as e:
        return f"Error retrieving tool catalog: {e}"


JIT_COT_CONVERTER_PROMPT = """You are an expert L1 IT Support Automation Engineer and OKF Playbook Architect.

Your task is to analyze a raw human SOP document (which may contain GUI click instructions, manual steps, or text descriptions) and convert it into a structured, execution-ready OKF Playbook JSON schema for automated agent execution.

## REGISTERED API TOOLS CATALOG
Below are the currently active API Tool Providers available in the system:
{available_tools_summary}

## 8-STAGE DEEP CoT REASONING MANDATE (WITH 4 MANDATORY VERIFICATION GATES)
You MUST follow these 8 reasoning stages in exact numerical order:

1. **Stage 1 (Tool-Catalog First Lookup & 4 Mandatory Verification Gates)**:
   Inspect the raw SOP text against the REGISTERED API TOOLS CATALOG above using these 4 strict Verification Gates:
   - **Gate 1 (Exact Function Match)**: Does the raw SOP action match an explicit function name declared in the catalog?
   - **Gate 2 (Active Provider Match)**: Is the provider name active and registered in the catalog?
   - **Gate 3 (Problem Alignment)**: Does the candidate tool function solve the exact problem described in the raw SOP?
   - **Gate 4 (Parameter Completeness)**: Are all 'required_inputs' declared by the tool function present or mapable to entities?

   * DECISION MANDATE:
     - IF ALL 4 Gates PASS -> Classify as a Tool Playbook step (`"step_type": "tool_call"`). Populate `"provider"`, `"function_name"`, and `"comm_inputs"`.
     - IF ANY Gate FAILS -> Classify as a Command Playbook step (`"step_type": "command"`). Translate GUI/text steps into exact Windows/Linux CLI shell commands with `"shell": "powershell"`.

2. **Stage 2 (Diagnostic & Remediation Sequence Ordering)**: Ensure non-destructive search/diagnostic steps (e.g. `search_users` or `ipconfig`) come FIRST before any corrective or account modification commands.

3. **Stage 3 (Precondition & Variable Extraction)**: Identify dynamic placeholders and ENFORCE strict double-brace format:
   - For `command` steps: Insert placeholders in command text (e.g. `{{entities.hostname}}`, `{{entities.executable}}`).
   - For `tool_call` steps: Insert placeholders in `comm_inputs` dictionary (e.g. `{{ "user_id": "{{entities.user_id}}" }}`).
   - Use `{{entities.var_name}}` for pre-configured entities (`{{entities.user_id}}`, `{{entities.hostname}}`, `{{entities.email}}`) and `{{variables.var_name}}` for runtime step outputs. DO NOT use un-nested single braces.

4. **Stage 4 (Strict SOP Command Fidelity & Fallbacks)**: Extract ONLY actions explicitly written in the raw SOP text. DO NOT invent or fabricate alternative fallback commands or tool calls. If not explicitly specified, set `"fallback_command": null`.

5. **Stage 5 (Verification & Output Parsing Instructions)**: Write clear regex/string inspection rules for `output_parse_instruction`:
   - For `command` steps: Inspect CLI stdout (e.g. "If output contains 'SUCCESS', set 'kill_confirmed' to 'true'").
   - For `tool_call` steps: Use the exact JSON field names declared in the tool's `Response Schema` above (e.g. "If response contains status='unlocked', set 'unlock_success' to 'true' and store response.user_id in variables.user_id").

6. **Stage 6 (100% Diagnostic Step Recall Mandate)**: You MUST extract EVERY SINGLE step described in the procedure section of the raw SOP text. Omitting any diagnostic or verification step is STRICTLY PROHIBITED.

7. **Stage 7 (Conditional Branch Mapping & execute_if)**: If the raw SOP specifies conditional skip instructions, map this logic into valid `execute_if` boolean expressions (e.g., `execute_if: variables.account_found == 'true'`).

8. **Stage 8 (Dynamic Timeout Allocation by Action Scope)**: Assign `timeout_seconds` dynamically: Quick Info Read / API Call (30s), System Scan / Diagnostic Audit (90s), Full Repair / Heavy Job (300s).

9. **CRITICAL MANDATE (Omit GUI Window Setup Steps)**: DO NOT generate non-executable GUI setup steps like "Open Command Prompt" or "Open Web Browser". Start directly with functional actions.


## OUTPUT JSON SCHEMA MANDATE
Output raw valid JSON only matching this schema:
```json
{{
    "reasoning_chain": [
        "[Stage 1 Verification Gates]: Gate 1 (Function match) -> Gate 2 (Provider active) -> Gate 3 (Problem aligned) -> Gate 4 (Params complete) -> Result: tool_call | command",
        "[Stage 2 Sequencing]: Ordered search/diagnostic steps before remediation",
        "[Stage 3 Variables]: Formatted {{entities.var}} placeholders",
        "[Stage 4 Fallbacks]: Mapped fallback actions",
        "[Stage 5 Verification]: Added output parse instructions",
        "[Stage 6 Recall]: Preserved 100% of diagnostic steps",
        "[Stage 7 Branching]: Mapped execute_if conditions",
        "[Stage 8 Timeouts]: Assigned timeout_seconds"
    ],
    "sop_id": "SOP-{{file_name_slug}}-001",
    "title": "Title of Playbook",
    "category": "network | storage | system | logins | software | hardware",
    "target_os": "windows | linux",
    "description": "Comprehensive overview of what this playbook does",
    "required_entities": ["user_id", "email", "hostname"],
    "trigger_words": ["unlock", "account", "login"],
    "steps": [
        {{
            "step_number": 1,
            "sop_step_description": "Detailed step objective",
            "step_type": "command | tool_call | verification | communication",
            "provider": "mock_support_platform (only for tool_call, else null)",
            "function_name": "unlock_user_account (only for tool_call, else null)",
            "comm_inputs": {{
                "user_id": "{{entities.user_id}}"
            }},
            "command": "ipconfig /all (only for command, else null)",
            "shell": "powershell (only for command, else null)",
            "fallback_command": null,
            "fallback_sop_id": null,
            "expected_output_contains": "unlocked",
            "timeout_seconds": 30,
            "output_variable": "step_result",
            "output_parse_instruction": "Inspect output/JSON response and set status flags.",
            "execute_if": null,
            "is_dangerous": false,
            "danger_warning": null
        }}
    ]
}}
```

## RAW SOP DOCUMENT TEXT TO TRANSLATE:
{raw_sop_text}
"""



def convert_raw_sop_to_okf(raw_filepath: str, override_sop_id: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """5-Stage CoT JIT Converter Node: Converts raw PDF/Docx/TXT SOP into an OKF Playbook.

    Composition of the two phases below. Retrieval's auto-discovery path uses
    this one-shot form; the operator-facing ingestion UI calls the phases
    separately so a human can review and edit the draft plan before anything is
    written to the knowledge base.
    """
    draft = plan_okf_from_raw(raw_filepath, override_sop_id=override_sop_id)
    okf_file_path = write_okf_playbook(draft, raw_filename=os.path.basename(raw_filepath))
    return okf_file_path, draft["frontmatter"]


def plan_okf_from_raw(raw_filepath: str, override_sop_id: Optional[str] = None) -> Dict[str, Any]:
    """Phase 1 (read-only): parse the raw SOP and draft the OKF playbook.

    Touches nothing on disk -- returns the proposed frontmatter plus the
    faithfulness-validation notes, so a reviewer can accept or correct the plan
    before `write_okf_playbook` commits it.
    """
    print(f"\n[JIT OKF Converter Agent Node] Universal MarkItDown parsing: {os.path.basename(raw_filepath)}...")

    parser_type, raw_text = extract_full_text(raw_filepath)
    if not raw_text or len(raw_text.strip()) < 10:
        raise ValueError(f"Could not extract text from raw file: {raw_filepath}")

    llm = get_llm("execution_planning", temperature=0)
    tools_summary = _get_formatted_api_tools_summary()
    prompt = JIT_COT_CONVERTER_PROMPT.format(
        available_tools_summary=tools_summary,
        raw_sop_text=raw_text
    )

    # 1. Invoke LLM for structured 5-Stage CoT JSON conversion
    res = llm.invoke(prompt)
    content = res.content if hasattr(res, "content") else str(res)

    match = re.search(r"(\{.*\})", content, re.DOTALL)
    clean_json = match.group(1) if match else content.strip()
    data = json.loads(clean_json)

    reasoning_chain = data.get("reasoning_chain") or []
    for stage_log in reasoning_chain:
        safe_log = str(stage_log).replace("→", "->").replace("↓", "v").replace("▶", ">").replace("◀", "<")
        print(f"  {safe_log}")

    sop_id_raw = data.get("sop_id") or ""
    raw_filename_base = os.path.splitext(os.path.basename(raw_filepath))[0]
    clean_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_filename_base).strip("-").upper()
    derived_id = clean_slug if clean_slug.startswith("SOP-") else f"SOP-{clean_slug[:20]}"

    if override_sop_id:
        sop_id = override_sop_id
    elif not sop_id_raw or "SOP-DYN-001" in sop_id_raw or "generate" in sop_id_raw.lower():
        sop_id = derived_id
    else:
        sop_id = sop_id_raw

    title = data.get("title", os.path.basename(raw_filepath))
    category = (data.get("category") or "other").lower().strip()
    target_os = data.get("target_os", "windows")
    description = data.get("description", f"Automated playbook for {title}.")
    
    steps = data.get("steps", [])

    # Normalize required_entities to standard entity keys
    has_command_step = any(s.get("step_type") == "command" or s.get("command") for s in steps)
    default_req = ["hostname", "email"] if has_command_step else ["email"]
    raw_req_entities = data.get("required_entities", default_req)
    if not has_command_step and "hostname" in raw_req_entities:
        raw_req_entities = [e for e in raw_req_entities if e != "hostname"]

    entity_key_map = {
        "computername": "hostname",
        "computer_name": "hostname",
        "target_host": "hostname",
        "target_machine": "hostname",
        "device_name": "hostname",
        "host": "hostname",
        "app_name": "application_name",
        "software_name": "application_name",
        "exe_name": "executable",
        "application_exe": "executable",
        "application_exe_name": "executable",
        "app_exe": "executable",
        "user_name": "username",
        "user": "username",
        "user_email": "email",
        "customer_email": "email",
        "user_identifier": "user_id",
        "account_id": "user_id",
    }
    required_entities = list(dict.fromkeys([entity_key_map.get(str(e).lower(), str(e)) for e in raw_req_entities]))

    trigger_words = data.get("trigger_words", [title])


    # Human SOP Faithfulness & Linkage Validation
    is_valid, validation_errors = validate_plan_faithfulness_and_linkage(raw_text, {"steps": steps})
    if not is_valid:
        safe_val = str(validation_errors).replace("→", "->").replace("↓", "v").replace("▶", ">").replace("◀", "<")
        print(f"[JIT Converter Warning] Plan validation notes: {safe_val}")

    # 2. Format Dual-Representation Frontmatter
    frontmatter_dict = {
        "type": "Playbook",
        "sop_id": sop_id,
        "title": title,
        "category": category,
        "target_os": target_os,
        "description": description,
        "required_entities": required_entities,
        "trigger_words": trigger_words,
        "steps": steps,
    }

    return {
        "frontmatter": frontmatter_dict,
        "parser_type": parser_type,
        "raw_chars": len(raw_text),
        "reasoning_chain": [str(s) for s in reasoning_chain],
        "is_valid": is_valid,
        "validation_errors": validation_errors or [],
    }


def write_okf_playbook(draft: Dict[str, Any], raw_filename: str = "(reviewed draft)") -> str:
    """Phase 2 (commits to disk): render the OKF body, save the playbook, then
    initialize its rulebook and refresh the catalogs and weekly audit log.

    `draft` is a `plan_okf_from_raw` result, optionally with its `frontmatter`
    edited by a human reviewer.
    """
    frontmatter_dict = draft["frontmatter"]
    sop_id = frontmatter_dict["sop_id"]
    title = frontmatter_dict["title"]
    category = (frontmatter_dict.get("category") or "other").lower().strip()
    frontmatter_dict["category"] = category
    description = frontmatter_dict.get("description", f"Automated playbook for {title}.")
    steps = frontmatter_dict.get("steps") or []

    yaml_header = yaml.dump(frontmatter_dict, sort_keys=False)
    markdown_body = f"# {title} Playbook\n\n## Overview\n{description}\n\n## Execution Steps\n"
    for s in steps:
        if s.get("step_type") == "tool_call":
            tool_name = f"{s.get('provider')}.{s.get('function_name')}"
            inputs_str = json.dumps(s.get("comm_inputs") or {})
            markdown_body += f"- **Step {s.get('step_number')}**: {s.get('sop_step_description')} [Tool Call: `{tool_name}({inputs_str})`]\n"
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

    print(f"[SUCCESS] JIT OKF Playbook saved to: {okf_file_path}")

    # 4. Auto-initialize Reflection Rulebook knowledge_base/patterns/<category>/rules_<SOP_ID>.md
    _initialize_reflection_rulebook(sop_id, title, category)

    # 5. Update Catalogs & Weekly Rotated System Log
    rel_path = f"{category}/{sop_id}.md"
    _update_sops_catalog_indexes()
    _log_okf_creation(sop_id, title, raw_filename, rel_path)

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
        print(f"[Memory Logger] Auto-initialized Reflection Rulebook: {rulebook_path}")


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
                        desc = post.metadata.get("description", "Playbook procedure.")
                        rel_path = f"{cat_name}/{filename}"
                        
                        entry = f"- [{title}](./{rel_path}) - Category: `{cat}` - {desc}"
                        cat_entries.append(f"- [{title}](./{filename}) - {desc}")
                        master_entries.append(entry)
                    except Exception as e:
                        print(f"[OKF Catalog Warning] Failed reading {filename}: {e}")

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
        header = f"# System Audit Log - Week {week_str}\n\n## 🛠️ Creation Events\n"
        with open(weekly_log_path, "w", encoding="utf-8") as f:
            f.write(header + log_entry)
    else:
        with open(weekly_log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
