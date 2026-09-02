import os
import json
import ast
import re
import datetime
import copy
import yaml
import frontmatter
from typing import Tuple, Dict, Any, Optional
from langchain_core.messages import HumanMessage, ToolMessage

# pyrefly: ignore [missing-import]
from config.llm_config import get_llm
# pyrefly: ignore [missing-import]
from core.document_parser import extract_ordered_sop_content
# pyrefly: ignore [missing-import]
from tools.tool_schemas import PLATFORM_SUMMARIES
# pyrefly: ignore [missing-import]
from tools.tool_functions import DYNAMIC_CATALOG_TOOLS
# pyrefly: ignore [missing-import]
from core.plan_validator import validate_plan_faithfulness_and_linkage
# pyrefly: ignore [missing-import]
from core.vlm_inspector import analyze_and_save_image
# pyrefly: ignore [missing-import]
from core.security import (
    escape_prompt_delimiters,
    compute_playbook_hmac,
    sanitize_slug,
    MAX_IMAGES_PER_SOP,
)
# pyrefly: ignore [missing-import]
from schemas import OKFPlaybookModel, OKFStepModel
# pyrefly: ignore [missing-import]
from prompts.jit_converter_prompts import (
    TRIAGE_ROUTER_PROMPT,
    COMMAND_COT_PROMPT,
    TOOL_COT_PROMPT,
    HYBRID_COT_PROMPT,
)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.getenv("ELONE_KB_DIR", os.path.join(BASE_DIR, "knowledge_base"))
SOPS_DIR = os.path.join(KB_DIR, "sops")
PATTERNS_DIR = os.path.join(KB_DIR, "patterns")
LOGS_DIR = os.path.join(KB_DIR, "logs")
CONVERTER_INPUT_LOGS_DIR = os.path.join(LOGS_DIR, "converter_input")
INDEX_PATH = os.path.join(SOPS_DIR, "index.md")


def _log_converter_input(raw_filepath: str, sop_slug: str, enriched_sop_text: str) -> str:
    """Audit log: saves the exact enriched SOP text (raw text + interleaved VLM
    image reports + scraped link context, in document order) that gets sent
    into the JIT converter LLM prompt, under knowledge_base/logs/converter_input/.
    """
    os.makedirs(CONVERTER_INPUT_LOGS_DIR, exist_ok=True)
    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
    filename = os.path.basename(raw_filepath)
    log_filename = f"{timestamp_str}_{sop_slug}_{filename}.log"
    log_path = os.path.join(CONVERTER_INPUT_LOGS_DIR, log_filename)

    header_lines = [
        "============================================================",
        "  SOP INGESTION PIPELINE — CONVERTER INPUT AUDIT LOG",
        "============================================================",
        f"  Source File:          {filename}",
        f"  Source Absolute Path: {os.path.abspath(raw_filepath)}",
        f"  SOP Slug:             {sop_slug}",
        f"  Character Count:      {len(enriched_sop_text)}",
        f"  Timestamp:            {now.strftime('%Y-%m-%d %H:%M:%S')}",
        "============================================================",
        "",
        "--- ENRICHED SOP TEXT SENT TO CONVERTER START ---",
        enriched_sop_text,
        "--- ENRICHED SOP TEXT SENT TO CONVERTER END ---",
        "",
    ]

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines))

    print(f"[JIT OKF Converter Agent] Saved converter input audit log ({len(enriched_sop_text)} chars) to: {log_path}")
    return log_path

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


def _run_triage_router(enriched_sop_text: str, sop_slug: str, override_sop_id: Optional[str] = None) -> Dict[str, Any]:
    """Stage 1: Dynamic Tool-Aware Intent Classifier & Router.
    Inspects live platform tools dynamically to classify into 'command', 'tool_call', 'hybrid', or 'unactionable'.
    """
    print(f"\n[Stage 1: Triage Router] Analyzing execution paradigm and candidate platforms...")
    triage_prompt = TRIAGE_ROUTER_PROMPT.replace("{raw_sop_text}", enriched_sop_text[:5000])
    llm = get_llm("execution_planning", temperature=0.0)

    tool_map = {t.name: t for t in DYNAMIC_CATALOG_TOOLS}
    llm_with_tools = llm.bind_tools(DYNAMIC_CATALOG_TOOLS)

    messages = [HumanMessage(content=triage_prompt)]
    max_tool_turns = 4
    content = ""

    for turn in range(max_tool_turns):
        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import check_daily_limit
            check_daily_limit("gemini")
        except Exception as q_err:
            if "Quota" in type(q_err).__name__ or "DailyQuotaExceededError" in str(type(q_err)):
                raise q_err

        res = llm_with_tools.invoke(messages)

        in_tok = 0
        out_tok = 0
        if hasattr(res, "usage_metadata") and res.usage_metadata:
            in_tok = res.usage_metadata.get("input_tokens", 0)
            out_tok = res.usage_metadata.get("output_tokens", 0)
        elif hasattr(res, "response_metadata") and res.response_metadata:
            tu = res.response_metadata.get("token_usage", {})
            in_tok = tu.get("prompt_tokens", 0)
            out_tok = tu.get("completion_tokens", 0)

        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import record_call
            record_call(
                caller="triage_router",
                model="gemini-3.7-flash" if "gemini" in str(type(llm)).lower() else "mistral-large-latest",
                provider="gemini" if "gemini" in str(type(llm)).lower() else "mistral",
                input_tokens=in_tok,
                output_tokens=out_tok,
                sop_id=override_sop_id or sop_slug
            )
        except Exception:
            pass

        if hasattr(res, "tool_calls") and res.tool_calls:
            messages.append(res)
            for tc in res.tool_calls:
                t_name = tc["name"]
                t_args = tc.get("args", {})
                print(f"[Stage 1: Triage Tool Inspection] Calling tool '{t_name}' with args: {t_args}...")
                if t_name in tool_map:
                    t_out = tool_map[t_name].invoke(t_args)
                else:
                    t_out = {"error": f"Tool '{t_name}' not found"}
                messages.append(ToolMessage(content=json.dumps(t_out), tool_call_id=tc["id"]))
        else:
            raw_c = res.content if hasattr(res, "content") else str(res)
            if isinstance(raw_c, list):
                raw_c = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c])
            content = raw_c
            break

    raw_c = content
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", str(raw_c), re.DOTALL)
    json_str = match.group(1) if match else (re.search(r"(\{.*\})", str(raw_c), re.DOTALL).group(1) if re.search(r"(\{.*\})", str(raw_c), re.DOTALL) else str(raw_c).strip())

    try:
        triage_data = json.loads(json_str)
        classification = triage_data.get("classification", "command").lower()
        is_exec = triage_data.get("is_executable", True)
        unexec_reason = triage_data.get("unexecutable_reason")
        conf_score = float(triage_data.get("confidence_score", 0.95))
        conf_level = triage_data.get("confidence_level", "High" if conf_score >= 0.85 else ("Medium" if conf_score >= 0.60 else "Low"))
        conf_reason = triage_data.get("confidence_reason", "Paradigm classified from document content analysis")

        print(f"[Stage 1: Triage Router] Classification: '{classification.upper()}' | Confidence: {conf_score:.2f} ({conf_level}) | Executable: {is_exec}")
        print(f"[Stage 1: Triage Router] Reason: {conf_reason}")
        print(f"[Stage 1: Triage Router] Summary: {triage_data.get('triage_summary', 'N/A')}")
        return {
            "classification": classification,
            "is_executable": is_exec,
            "unexecutable_reason": unexec_reason,
            "confidence_score": conf_score,
            "confidence_level": conf_level,
            "confidence_reason": conf_reason,
            "detected_platforms": triage_data.get("detected_platforms", []),
            "target_os": triage_data.get("target_os", "windows"),
            "requires_shell": triage_data.get("requires_shell", True),
        }
    except Exception as e:
        print(f"[Stage 1: Triage Router] Fallback parsing to 'command': {e}")
        return {
            "classification": "command",
            "is_executable": True,
            "unexecutable_reason": None,
            "confidence_score": 0.80,
            "confidence_level": "Medium",
            "confidence_reason": "Fallback default command classification",
            "detected_platforms": [],
            "target_os": "windows",
            "requires_shell": True,
        }


def convert_raw_sop_to_okf(raw_filepath: str, override_sop_id: Optional[str] = None) -> Tuple[Optional[str], Dict[str, Any]]:
    """5-Stage CoT JIT Converter Node: Converts raw PDF/Docx/TXT SOP into an OKF Playbook.

    Composition of the two phases below. Retrieval's auto-discovery path uses
    this one-shot form; the operator-facing ingestion UI calls the phases
    separately so a human can review and edit the draft plan before anything is
    written to the knowledge base.
    """
    draft = plan_okf_from_raw(raw_filepath, override_sop_id=override_sop_id)
    
    # Check if document is non-executable / not understandable as an automated procedure
    if draft.get("is_executable") is False or draft.get("frontmatter", {}).get("is_executable") is False:
        unexec_reason = draft.get("unexecutable_reason") or draft.get("frontmatter", {}).get("unexecutable_reason") or "SOP is not understandable as an automated procedure."
        print(f"[JIT Converter] Ingestion skipped: {unexec_reason}")
        metadata = dict(draft.get("frontmatter", {}))
        metadata["status"] = "unactionable"
        metadata["reason"] = unexec_reason
        return None, metadata

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
    print(f"\n[JIT OKF Converter Agent Node] Document-order-preserving parsing: {os.path.basename(raw_filepath)}...")

    raw_filename_base = os.path.splitext(os.path.basename(raw_filepath))[0]
    sop_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_filename_base).strip("-").upper()[:20]

    # Walk the document once, in its own physical order, so each image stays
    # anchored to the text step it illustrates (instead of being pulled out
    # and dumped as one block at the end).
    parser_type, segments = extract_ordered_sop_content(raw_filepath)

    raw_text = "\n\n".join(s["content"] for s in segments if s["type"] == "text")
    if not raw_text or len(raw_text.strip()) < 10:
        raise ValueError(f"Could not extract text from raw file: {raw_filepath}")

    # Extract embedded URLs and scrape reference knowledge (DISABLED: External link content omitted from LLM prompt for security)
    # embedded_urls = extract_urls_from_markdown(raw_text)
    # scraped_context_blocks = []
    knowledge_base_ref = []

    # if embedded_urls:
    #     print(f"[JIT OKF Converter Agent] Found {len(embedded_urls)} embedded URLs in SOP. Scraping reference pages...")
    #     for url in embedded_urls[:5]:  # Limit to top 5 links
    #         success, web_md, rel_cache_path = fetch_and_convert_url(url)
    #         if success and len(web_md.strip()) > 30:
    #             scraped_context_blocks.append(f"### Reference Web Page [{url}]:\n{web_md[:1500]}")
    #             knowledge_base_ref.append({
    #                 "url": url,
    #                 "file_path": rel_cache_path
    #             })

    # Rebuild the SOP text in the exact same order as the source document:
    # each image is analyzed by the Vision LLM and its report is spliced in
    # right where the image occurred, immediately after the text step above it.
    enriched_parts = []
    image_index = 0
    for seg in segments:
        if seg["type"] == "text":
            enriched_parts.append(seg["content"])
        else:
            image_index += 1
            if image_index > MAX_IMAGES_PER_SOP:
                print(f"[JIT Converter Security] Document contains more than {MAX_IMAGES_PER_SOP} images. Skipping image {image_index} to prevent token bloat.")
                continue
            label = seg.get("label", f"Image {image_index}")
            report_text, image_ref = analyze_and_save_image(seg["bytes"], seg["mime_type"], label, sop_slug, image_index)
            conf_score = float(image_ref.get("confidence_score", 0.90))

            if conf_score >= 0.85:
                directive = f"[HIGH CONFIDENCE: {conf_score:.2f} — Fully trust and extract visible UI buttons, IDs, and parameters]"
            elif conf_score >= 0.60:
                directive = f"[MEDIUM CONFIDENCE: {conf_score:.2f} — Use for supplementary context; prioritize written text if conflicting]"
            else:
                directive = f"[LOW CONFIDENCE: {conf_score:.2f} / UNRELIABLE — Rely strictly on surrounding written SOP text and do not guess unverified parameters]"

            enriched_parts.append(f"### Visual Inspection Report ({label}) {directive}:\n{report_text}")
            knowledge_base_ref.append(image_ref)

    raw_combined_text = "\n\n".join(enriched_parts)
    # Escape prompt sandbox delimiters to prevent container breakouts
    enriched_sop_text = escape_prompt_delimiters(raw_combined_text)

    # Scraped link context disabled for security (prevent indirect prompt injection)
    # if scraped_context_blocks:
    #     enriched_sop_text += "\n\n## LINKED REFERENCE KNOWLEDGE (Scraped from embedded SOP URLs):\n" + "\n\n".join(scraped_context_blocks)

    # Audit log: persist the exact document-order text (raw + interleaved VLM
    # image reports) that will be fed into the converter LLM.
    _log_converter_input(raw_filepath, sop_slug, enriched_sop_text)

    # -------------------------------------------------------------------------
    # STAGE 1: Fast LLM Intent Classifier & Triage Router (~250 tokens)
    # -------------------------------------------------------------------------
    triage_res = _run_triage_router(enriched_sop_text, sop_slug, override_sop_id)
    if not triage_res.get("is_executable", True) or triage_res.get("classification") == "unactionable":
        unexec_reason = triage_res.get("unexecutable_reason") or "Purely informational document with no actionable automated CLI commands or tool operations."
        print(f"[JIT Converter] Stage 1 Early Exit: Document identified as unactionable: {unexec_reason}")
        frontmatter_dict = {
            "sop_id": f"SOP-{sop_slug}-001",
            "title": sop_slug.replace("-", " ").title(),
            "platform": "system",
            "category": "system",
            "target_os": "windows",
            "description": unexec_reason,
            "confidence_score": 0.0,
            "confidence_level": "Low",
            "confidence_reason": unexec_reason,
            "is_executable": False,
            "unexecutable_reason": unexec_reason,
            "required_entities": [],
            "trigger_words": [],
            "steps": [],
        }
        return {
            "sop_id": f"SOP-{sop_slug}-001",
            "frontmatter": frontmatter_dict,
            "steps": [],
            "confidence_score": 0.0,
            "confidence_level": "Low",
            "confidence_reason": unexec_reason,
            "is_executable": False,
            "unexecutable_reason": unexec_reason,
            "is_valid": True,
            "validation_errors": [],
            "knowledge_base_ref": knowledge_base_ref,
        }

    # -------------------------------------------------------------------------
    # STAGE 2: Specialized Converter Selection (Command / Tool / Hybrid)
    # -------------------------------------------------------------------------
    classification = triage_res.get("classification", "command")
    if classification == "command":
        base_template = COMMAND_COT_PROMPT
        use_tools = False
        print(f"[Stage 2: Converter Dispatch] Selected 'COMMAND_COT_PROMPT' (0 tools bound | Pure PowerShell focus)")
    elif classification == "tool_call":
        base_template = TOOL_COT_PROMPT
        use_tools = True
        print(f"[Stage 2: Converter Dispatch] Selected 'TOOL_COT_PROMPT' (Dynamic Tool Calling enabled)")
    else: # hybrid
        base_template = HYBRID_COT_PROMPT
        use_tools = True
        print(f"[Stage 2: Converter Dispatch] Selected 'HYBRID_COT_PROMPT' (Cross-Paradigm Bridge)")

    # Closed-Loop Auto-Retry Engine (Max 3 Retries)
    max_retries = 3
    feedback_history = []

    last_data = None
    last_is_valid = False
    last_validation_errors = []

    for attempt in range(1, max_retries + 1):
        temp = 0.0 if attempt == 1 else 0.1
        llm = get_llm("execution_planning", temperature=temp)

        retry_sop_text = enriched_sop_text
        if feedback_history:
            retry_sop_text += "\n\n## PREVIOUS ATTEMPT ERRORS (MUST FIX ON THIS RETRY):\n" + "\n".join(feedback_history)

        prompt = base_template.replace("{raw_sop_text}", retry_sop_text)

        if attempt > 1:
            print(f"\n[JIT Converter Auto-Retry] Attempt {attempt}/{max_retries} with feedback injection...")

        # Bind tools conditionally: 0 tools for pure command SOPs to save tokens
        tool_map = {t.name: t for t in DYNAMIC_CATALOG_TOOLS}
        if use_tools:
            llm_with_tools = llm.bind_tools(DYNAMIC_CATALOG_TOOLS)
        else:
            llm_with_tools = llm

        # Multi-turn tool calling conversation loop
        messages = [HumanMessage(content=prompt)]
        max_tool_turns = 5
        content = ""
        executed_tool_cache = {}

        for turn in range(max_tool_turns):
            try:
                # pyrefly: ignore [missing-import]
                from gemini_monitor.monitor import check_daily_limit, record_call
                check_daily_limit("gemini")
            except Exception as q_err:
                if "Quota" in type(q_err).__name__ or "DailyQuotaExceededError" in str(type(q_err)):
                    raise q_err

            res = llm_with_tools.invoke(messages)
            messages.append(res)

            # Record token usage in gemini_monitor
            in_tok = 0
            out_tok = 0
            if hasattr(res, "usage_metadata") and res.usage_metadata:
                in_tok = res.usage_metadata.get("input_tokens", 0)
                out_tok = res.usage_metadata.get("output_tokens", 0)
            elif hasattr(res, "response_metadata") and res.response_metadata:
                tu = res.response_metadata.get("token_usage", {})
                in_tok = tu.get("prompt_tokens", 0)
                out_tok = tu.get("completion_tokens", 0)
            
            try:
                # pyrefly: ignore [missing-import]
                from gemini_monitor.monitor import record_call
                record_call(
                    caller="execution_planning",
                    model="gemini-3.7-flash" if "gemini" in str(type(llm)).lower() else "mistral-large-latest",
                    provider="gemini" if "gemini" in str(type(llm)).lower() else "mistral",
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    sop_id=override_sop_id or sop_slug
                )
            except Exception as mon_err:
                pass

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
            if not isinstance(data, dict):
                raise ValueError("Parsed JSON must be a dictionary object.")

            is_exec = data.get("is_executable", True)
            if is_exec is False or len(data.get("steps", [])) == 0:
                unexec_reason = data.get("unexecutable_reason") or "Raw SOP document contains zero executable procedural steps."
                print(f"[JIT Converter] Document identified as non-executable / unactionable: {unexec_reason}")
                data["is_executable"] = False
                data["unexecutable_reason"] = unexec_reason
                validated_model = OKFPlaybookModel.model_validate(data)
                data = validated_model.model_dump()
                
                return {
                    "frontmatter": {
                        "type": "Playbook",
                        "sop_id": None,
                        "title": data.get("title", os.path.basename(raw_filepath)),
                        "platform": "system",
                        "category": (data.get("category") or "other").lower().strip(),
                        "target_os": data.get("target_os", "windows"),
                        "description": data.get("description", "Non-executable document."),
                        "is_executable": False,
                        "unexecutable_reason": unexec_reason,
                        "confidence_score": 0.0,
                        "confidence_level": "Low",
                        "confidence_reason": unexec_reason,
                        "required_entities": [],
                        "trigger_words": [],
                        "steps": [],
                    },
                    "is_executable": False,
                    "unexecutable_reason": unexec_reason,
                    "parser_type": parser_type,
                    "raw_chars": len(raw_text),
                    "reasoning_chain": [str(s) for s in (data.get("reasoning_chain") or [])],
                    "confidence_score": 0.0,
                    "confidence_level": "Low",
                    "confidence_reason": unexec_reason,
                    "is_valid": True,
                    "validation_errors": [],
                }

            validated_model = OKFPlaybookModel.model_validate(data)
            data = validated_model.model_dump()
        except Exception as pydantic_err:
            err_str = str(pydantic_err)
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
            # If failure is due to fabricated placeholder steps, bail out immediately
            if any("placeholder step" in str(e).lower() for e in (validation_errors or [])):
                raise ValueError(f"Ingestion blocked: Playbook failed validation with errors: {validation_errors}")

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
    confidence_score = float(data.get("confidence_score") if data.get("confidence_score") is not None else 0.95)
    confidence_level = str(data.get("confidence_level") or "High")
    confidence_reason = data.get("confidence_reason") or "Conversion completed with verified tool mappings and procedural fidelity."
    steps = data.get("steps", [])

    print(f"\n[JIT Converter Agent] Final Output Confidence: {confidence_score:.2f} ({confidence_level}) | Reason: {confidence_reason}")

    has_command_step = any(s.get("step_type") == "command" or s.get("command") for s in steps)
    default_req = ["hostname", "email"] if has_command_step else ["email"]
    raw_req_entities = data.get("required_entities", default_req)
    if not has_command_step and "hostname" in raw_req_entities:
        raw_req_entities = [e for e in raw_req_entities if e != "hostname"]

    required_entities = list(dict.fromkeys([ENTITY_KEY_MAP.get(str(e).lower(), str(e)) for e in raw_req_entities]))
    trigger_words = data.get("trigger_words", [title])
    platform = data.get("platform")
    if not platform:
        for s in steps:
            if s.get("platform"):
                platform = s.get("platform")
                break
    platform = platform or "system"

    # Ensure platform is in trigger_words for fast lookup
    if platform and platform != "system" and platform.lower() not in [t.lower() for t in trigger_words]:
        trigger_words.insert(0, platform)

    # 2. Format Dual-Representation Frontmatter
    frontmatter_dict = {
        "type": "Playbook",
        "sop_id": sop_id,
        "title": title,
        "platform": platform,
        "category": category,
        "target_os": target_os,
        "description": description,
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "confidence_reason": confidence_reason,
        "is_executable": True,
        "unexecutable_reason": None,
        "required_entities": required_entities,
        "trigger_words": trigger_words,
        "steps": steps,
    }

    return {
        "frontmatter": frontmatter_dict,
        "is_executable": True,
        "unexecutable_reason": None,
        "parser_type": parser_type,
        "raw_chars": len(raw_text),
        "reasoning_chain": [str(s) for s in reasoning_chain],
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "confidence_reason": confidence_reason,
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

    # Cryptographic Playbook Integrity Stamp (HMAC-SHA256)
    clean_frontmatter["integrity_hmac_sha256"] = compute_playbook_hmac(clean_frontmatter.get("steps", []))

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
                        platform = post.metadata.get("platform", "system")
                        desc = post.metadata.get("description", "Playbook procedure.")
                        triggers = post.metadata.get("trigger_words", [])
                        triggers_str = ", ".join(triggers) if isinstance(triggers, list) else str(triggers)
                        rel_path = f"{cat_name}/{filename}"
                        
                        entry = f"- [{title}](./{rel_path}) | Platform: `{platform}` | Category: `{cat}` | Triggers: `{triggers_str}` | {desc}"
                        cat_entries.append(f"- [{title}](./{filename}) | Platform: `{platform}` | Triggers: `{triggers_str}` | {desc}")
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
