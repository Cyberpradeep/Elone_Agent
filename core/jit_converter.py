import os
import json
import ast
import re
import datetime
import yaml
import frontmatter
from typing import Tuple, Dict, Any, Optional
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from config.llm_config import get_llm
from tools.tool_schemas import PLATFORM_SUMMARIES
from tools.tool_functions import DYNAMIC_CATALOG_TOOLS
from core.document_parser import extract_full_text
from core.plan_validator import validate_plan_faithfulness_and_linkage
from core.link_scraper import extract_urls_from_markdown, fetch_and_convert_url
from core.vlm_inspector import process_sop_images
from core.okf_schema import OKFPlaybookModel, OKFStepModel
from prompts.jit_converter_prompts import JIT_COT_CONVERTER_PROMPT


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
LOGS_DIR = os.path.join(KB_DIR, "logs")
INDEX_PATH = os.path.join(SOPS_DIR, "index.md")

ENTITY_KEY_MAP = {
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


def convert_raw_sop_to_okf(raw_filepath: str, override_sop_id: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """5-Stage CoT JIT Converter Node: Converts raw PDF/Docx/TXT SOP into an OKF Playbook.

    Composition of the two phases below. Retrieval's auto-discovery path uses
    this one-shot form; the operator-facing ingestion UI calls the phases
    separately so a human can review and edit the draft plan before anything is
    written to the knowledge base.
    """
    draft = plan_okf_from_raw(raw_filepath, override_sop_id=override_sop_id)
    
    # Bug #3 Fix: Block disk write if plan failed faithfulness & linkage validation
    if not draft.get("is_valid", False):
        err_details = draft.get("validation_errors", ["Plan validation failed"])
        raise ValueError(f"Ingestion blocked: Playbook failed validation with errors: {err_details}")

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

    # Extract embedded URLs and scrape reference knowledge
    embedded_urls = extract_urls_from_markdown(raw_text)
    scraped_context_blocks = []
    knowledge_base_ref = []

    if embedded_urls:
        print(f"[JIT OKF Converter Agent] Found {len(embedded_urls)} embedded URLs in SOP. Scraping reference pages...")
        for url in embedded_urls[:5]:  # Limit to top 5 links
            success, web_md, rel_cache_path = fetch_and_convert_url(url)
            if success and len(web_md.strip()) > 30:
                scraped_context_blocks.append(f"### Reference Web Page [{url}]:\n{web_md[:1500]}")
                knowledge_base_ref.append({
                    "url": url,
                    "file_path": rel_cache_path
                })

    # Extract embedded images and run Gemini VLM Visual Inspection
    raw_filename_base = os.path.splitext(os.path.basename(raw_filepath))[0]
    sop_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_filename_base).strip("-").upper()[:20]
    vlm_result = process_sop_images(raw_filepath, sop_slug)

    if vlm_result.get("image_refs"):
        knowledge_base_ref.extend(vlm_result["image_refs"])

    enriched_sop_text = raw_text
    if vlm_result.get("summary_text"):
        enriched_sop_text += "\n\n## EXTRACTED VISUAL CONTROL METADATA (VLM INFERENCE):\n" + vlm_result["summary_text"]

    if scraped_context_blocks:
        enriched_sop_text += "\n\n## LINKED REFERENCE KNOWLEDGE (Scraped from embedded SOP URLs):\n" + "\n\n".join(scraped_context_blocks)

    # Closed-Loop Auto-Retry Engine (Max 3 Retries)
    max_retries = 3
    feedback_history = []

    last_data = None
    last_is_valid = False
    last_validation_errors = []

    for attempt in range(1, max_retries + 1):
        temp = 0.0 if attempt == 1 else 0.1
        llm = get_llm("execution_planning", temperature=temp)
        # 1. Build lightweight platform overview (~100 tokens)
        platform_summary_lines = [
            f"- Platform: '{p['platform']}' (Provider: '{p['provider']}') — {p['description']}"
            for p in PLATFORM_SUMMARIES
        ]
        platforms_overview = "\n".join(platform_summary_lines)

        retry_sop_text = enriched_sop_text
        if feedback_history:
            retry_sop_text += "\n\n## PREVIOUS ATTEMPT ERRORS (MUST FIX ON THIS RETRY):\n" + "\n".join(feedback_history)

        prompt = JIT_COT_CONVERTER_PROMPT.format(
            available_tools_summary=platforms_overview,
            raw_sop_text=retry_sop_text
        )

        if attempt > 1:
            print(f"\n[JIT Converter Auto-Retry] Attempt {attempt}/{max_retries} with feedback injection...")

        # 2. Bind LangChain dynamic tools to LLM
        tool_map = {t.name: t for t in DYNAMIC_CATALOG_TOOLS}
        llm_with_tools = llm.bind_tools(DYNAMIC_CATALOG_TOOLS)

        # Multi-turn tool calling conversation loop
        messages = [HumanMessage(content=prompt)]
        max_tool_turns = 5
        content = ""
        executed_tool_cache = {}

        for turn in range(max_tool_turns):
            res = llm_with_tools.invoke(messages)
            messages.append(res)

            # Check if LLM invoked any dynamic tools
            if hasattr(res, "tool_calls") and res.tool_calls:
                for tc in res.tool_calls:
                    t_name = tc.get("name", "")
                    t_args = tc.get("args", {})
                    t_id = tc.get("id") or f"call_{turn}"
                    cache_key = f"{t_name}:{json.dumps(t_args, sort_keys=True)}"

                    if cache_key in executed_tool_cache:
                        t_output = executed_tool_cache[cache_key]
                        output_json_str = json.dumps(t_output, indent=2, default=str)
                        messages.append(ToolMessage(content=output_json_str, tool_call_id=t_id))
                        continue

                    if t_name in tool_map:
                        try:
                            t_output = tool_map[t_name].invoke(t_args)
                        except Exception as t_err:
                            t_output = {"error": f"Tool execution failed: {t_err}"}
                    else:
                        t_output = {"error": f"Unknown tool '{t_name}'. Available: {list(tool_map.keys())}"}

                    executed_tool_cache[cache_key] = t_output
                    output_json_str = json.dumps(t_output, indent=2, default=str)

                    # Clean atomic CLI logging with flush=True
                    preview = output_json_str if len(output_json_str) <= 350 else output_json_str[:350] + f"\n... [{len(output_json_str)} total characters]"
                    safe_preview = preview.encode("ascii", errors="replace").decode("ascii")
                    log_block = (
                        f"\n{'='*55}\n"
                        f"[Dynamic Tool Invocation] LLM called: {t_name}({t_args})\n"
                        f"[Dynamic Tool Result] Output from '{t_name}':\n{safe_preview}\n"
                        f"{'='*55}\n"
                    )
                    print(log_block, flush=True)

                    messages.append(ToolMessage(content=output_json_str, tool_call_id=t_id))
            else:
                raw_c = res.content if hasattr(res, "content") else str(res)
                if isinstance(raw_c, list):
                    content = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c])
                else:
                    content = str(raw_c)
                break

        # Scenario 1: JSON Syntax Extraction & Handling (3-Tier Resilient Parser)
        match = re.search(r"```(?:json|python)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        clean_json = match.group(1) if match else (re.search(r"(\{.*\})", content, re.DOTALL).group(1) if re.search(r"(\{.*\})", content, re.DOTALL) else content.strip())
        clean_json = re.sub(r"^\s*\{\{", "{", clean_json)
        clean_json = re.sub(r"\}\}\s*$", "}", clean_json)
        clean_json = re.sub(r",\s*([\]}])", r"\1", clean_json)

        data = None

        # Tier 1: Standard RFC JSON
        try:
            data = json.loads(clean_json)
        except Exception:
            pass

        # Tier 2: Python AST Literal (handles single quotes, True, False, None)
        if data is None:
            try:
                data = ast.literal_eval(clean_json)
            except Exception:
                pass

        # Tier 3: Regex single-to-double quote and boolean normalization fallback
        if data is None:
            try:
                normalized = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', clean_json)
                normalized = re.sub(r"\bTrue\b", "true", normalized)
                normalized = re.sub(r"\bFalse\b", "false", normalized)
                normalized = re.sub(r"\bNone\b", "null", normalized)
                data = json.loads(normalized)
            except Exception as json_err:
                err_msg = f"Scenario 1 Error (Attempt {attempt}): JSON Parsing Failed: {json_err}"
                print(f"[JIT Converter Warning] {err_msg}")
                feedback_history.append(f"- {err_msg}. MANDATE: Enforce valid JSON output format with standard double quotes.")
                continue

        # Scenario 2: Pydantic Schema Model Validation
        try:
            # Normalize steps if present for pydantic
            if "steps" in data and isinstance(data["steps"], list):
                validated_model = OKFPlaybookModel.model_validate(data)
                data = validated_model.model_dump()
        except Exception as pydantic_err:
            err_msg = f"Scenario 2 Error (Attempt {attempt}): Pydantic Schema Violation: {pydantic_err}"
            print(f"[JIT Converter Warning] {err_msg}")
            feedback_history.append(f"- {err_msg}")
            continue

        steps = data.get("steps", [])

        # Scenario 3 & Scenario 4: Layer 1 Rule & Layer 2 Faithfulness Validation
        is_valid, validation_errors = validate_plan_faithfulness_and_linkage(raw_text, {"steps": steps})
        last_data = data
        last_is_valid = is_valid
        last_validation_errors = validation_errors or []

        if not is_valid:
            safe_val = str(validation_errors).replace("→", "->").replace("↓", "v").replace("▶", ">").replace("◀", "<")
            err_msg = f"Scenario 3/4 Validation Error (Attempt {attempt}): {safe_val}"
            print(f"[JIT Converter Warning] Plan validation failed: {safe_val}")
            feedback_history.append(f"- {err_msg}")
            continue

        # All 4 Scenarios Passed Cleanly!
        print(f"[JIT Converter Auto-Retry] Conversion succeeded on Attempt {attempt}/{max_retries}!")
        break

    if not last_data:
        raise ValueError(f"Ingestion blocked: LLM failed all {max_retries} retry attempts with errors: {feedback_history}")

    data = last_data
    is_valid = last_is_valid
    validation_errors = last_validation_errors

    reasoning_chain = data.get("reasoning_chain") or []
    for stage_log in reasoning_chain:
        safe_log = str(stage_log).replace("→", "->").replace("↓", "v").replace("▶", ">").replace("◀", "<")
        print(f"  {safe_log}")

    sop_id_raw = data.get("sop_id") or ""
    raw_filename_base = os.path.splitext(os.path.basename(raw_filepath))[0]
    clean_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_filename_base).strip("-").upper()
    clean_slug_truncated = clean_slug.replace("SOP-", "")[:20]
    derived_id = f"SOP-{clean_slug_truncated}"

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

    has_command_step = any(s.get("step_type") == "command" or s.get("command") for s in steps)
    default_req = ["hostname", "email"] if has_command_step else ["email"]
    raw_req_entities = data.get("required_entities", default_req)
    if not has_command_step and "hostname" in raw_req_entities:
        raw_req_entities = [e for e in raw_req_entities if e != "hostname"]

    required_entities = list(dict.fromkeys([ENTITY_KEY_MAP.get(str(e).lower(), str(e)) for e in raw_req_entities]))
    trigger_words = data.get("trigger_words", [title])

    # 2. Format Dual-Representation Frontmatter
    frontmatter_dict = {
        "type": "Playbook",
        "sop_id": sop_id,
        "title": title,
        "category": category,
        "target_os": target_os,
        "description": description,
        "knowledge_base_ref": knowledge_base_ref,
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
    knowledge_base_ref = frontmatter_dict.get("knowledge_base_ref") or []
    steps = frontmatter_dict.get("steps") or []

    yaml_header = yaml.dump(frontmatter_dict, sort_keys=False)
    markdown_body = f"# {title} Playbook\n\n## Overview\n{description}\n\n"
    
    if knowledge_base_ref:
        markdown_body += "## Knowledge Base References\n"
        for kb_item in knowledge_base_ref:
            if "url" in kb_item:
                markdown_body += f"- [{kb_item['url']}]({kb_item['url']}) — Knowledge File: `{kb_item['file_path']}`\n"
            elif "image_path" in kb_item:
                markdown_body += f"- Image Screenshot: `{kb_item['image_path']}` — Visual Audit Metadata: `{kb_item['file_path']}`\n"
        markdown_body += "\n"

    markdown_body += "## Execution Steps\n"
    for s in steps:
        if s.get("step_type") == "tool_call":
            platform_prefix = f"Platform: `{s.get('platform')}` | " if s.get("platform") else ""
            tool_name = f"{s.get('provider')}.{s.get('function_name')}"
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
        header = f"# System Audit Log - Week {week_str}\n\n## Creation Events\n"
        with open(weekly_log_path, "w", encoding="utf-8") as f:
            f.write(header + log_entry)
    else:
        with open(weekly_log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
