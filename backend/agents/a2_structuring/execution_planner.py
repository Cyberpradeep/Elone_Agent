"""
Agent A2: JIT Execution Planner
===============================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.2)
Stage 2: 6-Stage Command CoT reasoning & dynamic tool binding.
Compiles raw SOP segments into a validated, deterministic OKF draft plan.
"""

import os
import re
import json
import ast
import datetime
from typing import Tuple, Dict, Any, Optional
from langchain_core.messages import HumanMessage, ToolMessage

# pyrefly: ignore [missing-import]
from config.llm_config import get_llm
# pyrefly: ignore [missing-import]
from tools.tool_functions import DYNAMIC_CATALOG_TOOLS
# pyrefly: ignore [missing-import]
from agents.a4_verification.plan_validator import validate_plan_faithfulness_and_linkage
from utils.security import escape_prompt_delimiters
from config.settings import get_max_images_per_sop, get_execution_mode
# pyrefly: ignore [missing-import]
from schemas import OKFPlaybookModel
# pyrefly: ignore [missing-import]
from prompts.jit_converter_prompts import (
    COMMAND_COT_PROMPT,
    TOOL_COT_PROMPT,
    HYBRID_COT_PROMPT,
)

from agents.a1_ingestion.document_extractor import extract_ordered_sop_content
from agents.a1_ingestion.vlm_extractor import analyze_and_save_image
from agents.a2_structuring.triage_router import run_triage_router, ENTITY_KEY_MAP
from agents.a2_structuring.okf_builder import write_okf_playbook

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
LOGS_DIR = os.path.join(KB_DIR, "logs")
CONVERTER_INPUT_LOGS_DIR = os.path.join(LOGS_DIR, "converter_input")


def _log_converter_input(raw_filepath: str, sop_slug: str, enriched_sop_text: str) -> str:
    """Audit log: saves the exact enriched SOP text (raw text + interleaved VLM
    image reports in document order) sent into converter LLM.
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


def plan_okf_from_raw(raw_filepath: str, override_sop_id: Optional[str] = None, feedback_override: Optional[Any] = None) -> Dict[str, Any]:
    """Phase 1 (read-only): parse the raw SOP and draft the OKF playbook.
    Touches nothing on disk -- returns the proposed frontmatter plus the
    faithfulness-validation notes, so a reviewer can accept or correct the plan.
    Supports feedback_override from Agent A4 correction loops (Section 7).
    """
    print(f"\n[JIT OKF Converter Agent Node] Document-order-preserving parsing: {os.path.basename(raw_filepath)}...")

    raw_filename_base = os.path.splitext(os.path.basename(raw_filepath))[0]
    sop_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_filename_base).strip("-").upper()[:20]

    parser_type, segments = extract_ordered_sop_content(raw_filepath)

    raw_text = "\n\n".join(s["content"] for s in segments if s["type"] == "text")
    if not raw_text or len(raw_text.strip()) < 10:
        raise ValueError(f"Could not extract text from raw file: {raw_filepath}")

    knowledge_base_ref = []
    enriched_parts = []
    image_index = 0
    for seg in segments:
        if seg["type"] == "text":
            enriched_parts.append(seg["content"])
        else:
            image_index += 1
            max_sop_images = get_max_images_per_sop()
            if image_index > max_sop_images:
                print(f"[JIT Converter Security] Document contains more than {max_sop_images} images. Skipping image {image_index}.")
                continue
            label = seg.get("label", f"Image {image_index}")
            report_text, image_ref = analyze_and_save_image(seg["bytes"], seg["mime_type"], label, sop_slug, image_index)
            conf_score = float(image_ref.get("confidence_score", 0.90))

            if conf_score >= 0.85:
                directive = f"[HIGH CONFIDENCE: {conf_score:.2f} — Fully trust and extract visible UI buttons, IDs, and parameters]"
            elif conf_score >= 0.60:
                directive = f"[MEDIUM CONFIDENCE: {conf_score:.2f} — Use for supplementary context; prioritize written text if conflicting]"
            else:
                directive = f"[LOW CONFIDENCE: {conf_score:.2f} / UNRELIABLE — Rely strictly on surrounding written SOP text]"

            enriched_parts.append(f"### Visual Inspection Report ({label}) {directive}:\n{report_text}")
            knowledge_base_ref.append(image_ref)

    raw_combined_text = "\n\n".join(enriched_parts)
    enriched_sop_text = escape_prompt_delimiters(raw_combined_text)

    _log_converter_input(raw_filepath, sop_slug, enriched_sop_text)

    # -------------------------------------------------------------------------
    # STAGE 1: Triage Router
    # -------------------------------------------------------------------------
    triage_res = run_triage_router(enriched_sop_text, sop_slug, override_sop_id)
    if not triage_res.get("is_executable", True) or triage_res.get("classification") == "unactionable":
        unexec_reason = triage_res.get("unexecutable_reason") or "Purely informational document with no actionable automated commands."
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
    # STAGE 2: Specialized Converter Selection
    # -------------------------------------------------------------------------
    if get_execution_mode() == "command_only":
        classification = "command"
        base_template = COMMAND_COT_PROMPT
        use_tools = False
        print(f"[Stage 2: Converter Dispatch] Execution Mode: 'command_only' enforced (Selected 'COMMAND_COT_PROMPT' | 0 tools bound | Pure Shell/PowerShell focus)")
    else:
        classification = triage_res.get("classification", "command")
        if classification == "command":
            base_template = COMMAND_COT_PROMPT
            use_tools = False
            print(f"[Stage 2: Converter Dispatch] Selected 'COMMAND_COT_PROMPT' (0 tools bound | Pure PowerShell focus)")
        elif classification == "tool_call":
            base_template = TOOL_COT_PROMPT
            use_tools = True
            print(f"[Stage 2: Converter Dispatch] Selected 'TOOL_COT_PROMPT' (Dynamic Tool Calling enabled)")
        else:
            base_template = HYBRID_COT_PROMPT
            use_tools = True
            print(f"[Stage 2: Converter Dispatch] Selected 'HYBRID_COT_PROMPT' (Cross-Paradigm Bridge)")

    max_retries = 3
    feedback_history = list(feedback_override) if feedback_override else []
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

        tool_map = {t.name: t for t in DYNAMIC_CATALOG_TOOLS}
        llm_with_tools = llm.bind_tools(DYNAMIC_CATALOG_TOOLS) if use_tools else llm

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
            except Exception:
                pass

            if hasattr(res, "tool_calls") and res.tool_calls:
                for tc in res.tool_calls:
                    t_name = tc.get("name", "")
                    t_args = tc.get("args", {})
                    t_id = tc.get("id") or f"call_{turn}"
                    cache_key = f"{t_name}:{json.dumps(t_args, sort_keys=True)}"

                    if cache_key in executed_tool_cache:
                        t_output = executed_tool_cache[cache_key]
                        output_json_str = json.dumps(t_output, separators=(',', ':'), default=str)
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
                    output_json_str = json.dumps(t_output, separators=(',', ':'), default=str)
                    messages.append(ToolMessage(content=output_json_str, tool_call_id=t_id))
            else:
                raw_c = res.content if hasattr(res, "content") else str(res)
                if isinstance(raw_c, list):
                    content = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c])
                else:
                    content = str(raw_c)
                break

        # JSON parsing
        clean_json = content.strip()
        code_fence_match = re.search(r"```(?:json|python)?\s*([\s\S]*?)\s*```", content, re.DOTALL)
        if code_fence_match:
            block = code_fence_match.group(1).strip()
            brace_match = re.search(r"(\{[\s\S]*\})", block)
            clean_json = brace_match.group(1) if brace_match else block
        else:
            brace_match = re.search(r"(\{[\s\S]*\})", content)
            if brace_match:
                clean_json = brace_match.group(1)

        clean_json = re.sub(r"^\s*\{\{", "{", clean_json)
        clean_json = re.sub(r"\}\}\s*$", "}", clean_json)
        clean_json = re.sub(r",\s*([\]}])", r"\1", clean_json)

        data = None
        json_err_msg = ""
        try:
            data = json.loads(clean_json)
        except Exception as e1:
            json_err_msg = str(e1)

        if data is None:
            try:
                data = ast.literal_eval(clean_json)
            except Exception:
                pass

        if data is None:
            # Only attempt single-to-double quote substitution if text uses Python single-quoted keys ({'key': ...})
            # This prevents destroying English contractions (e.g. User's, doesn't) in standard JSON
            has_single_quoted_keys = bool(re.search(r"\{\s*'|\n\s*'[\w_-]+'\s*:", clean_json))
            if has_single_quoted_keys:
                try:
                    normalized = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', clean_json)
                    normalized = re.sub(r"\bTrue\b", "true", normalized)
                    normalized = re.sub(r"\bFalse\b", "false", normalized)
                    normalized = re.sub(r"\bNone\b", "null", normalized)
                    data = json.loads(normalized)
                except Exception:
                    pass

        if data is None:
            err_msg = f"Scenario 1 Error (Attempt {attempt}): JSON Parsing Failed: {json_err_msg or 'Invalid JSON syntax'}"
            print(f"[JIT Converter Warning] {err_msg}")
            feedback_history.append(f"- {err_msg}. MANDATE: Enforce valid JSON output format without truncation.")
            continue

        # Schema Validation
        try:
            if not isinstance(data, dict):
                raise ValueError("Parsed JSON must be a dictionary object.")

            # Filter out non-executable steps (e.g. manual_ui_omitted) erroneously placed in 'steps'
            raw_steps = data.get("steps", [])
            if isinstance(raw_steps, list):
                clean_steps = []
                coverage_list = data.setdefault("source_action_coverage", [])
                for s in raw_steps:
                    if not isinstance(s, dict):
                        continue
                    st = str(s.get("step_type", "")).lower().strip()
                    if st in {"manual_ui_omitted", "omitted", "ui_omitted", "manual"}:
                        action_desc = s.get("sop_step_description") or s.get("name") or "Manual UI action"
                        coverage_list.append({
                            "source_action": action_desc,
                            "coverage": "manual_ui_omitted",
                            "reason": s.get("step_reasoning") or "Manual/UI step omitted from automated execution.",
                        })
                    else:
                        clean_steps.append(s)
                for idx, s in enumerate(clean_steps, 1):
                    s["step_number"] = idx
                data["steps"] = clean_steps

            is_exec = data.get("is_executable", True)
            if is_exec is False or len(data.get("steps", [])) == 0:
                unexec_reason = data.get("unexecutable_reason") or "Raw SOP document contains zero executable steps."
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
            err_msg = f"Scenario 2 Error (Attempt {attempt}): Pydantic Schema Violation: {pydantic_err}"
            print(f"[JIT Converter Warning] {err_msg}")
            feedback_history.append(f"- {err_msg}")
            continue

        steps = data.get("steps", [])

        # Harmonize and align source_action_coverage with actual steps
        coverage_items = data.get("source_action_coverage")
        if isinstance(coverage_items, list):
            tool_to_step = {}
            for s in steps:
                if isinstance(s, dict) and s.get("step_type") == "tool_call":
                    plat = s.get("platform")
                    fn = s.get("function_name")
                    step_num = s.get("step_number")
                    if fn:
                        canonical = f"{plat}.{fn}" if plat else fn
                        tool_to_step[canonical] = step_num
                        tool_to_step[fn] = step_num

            for item in coverage_items:
                if not isinstance(item, dict):
                    continue
                cov = str(item.get("coverage", "")).lower().strip()
                if cov in {"manual_ui_omitted", "unsupported_required"}:
                    item["step_number"] = None
                    if not item.get("reason"):
                        item["reason"] = "Manual UI action omitted from automated execution."
                elif cov == "tool_covered":
                    tool = str(item.get("tool", "")).strip()
                    if tool in tool_to_step:
                        item["step_number"] = tool_to_step[tool]
                    elif "." in tool:
                        fn_only = tool.split(".", 1)[1]
                        if fn_only in tool_to_step:
                            item["step_number"] = tool_to_step[fn_only]

        # Faithfulness & Linkage Validation
        is_valid, validation_errors = validate_plan_faithfulness_and_linkage(
            raw_text,
            {
                "steps": steps,
                "required_entities": data.get("required_entities") or [],
                "source_action_coverage": data.get("source_action_coverage") or [],
                "automation_status": data.get("automation_status", "fully_automated"),
            },
        )
        last_data = data
        last_is_valid = is_valid
        last_validation_errors = validation_errors or []

        if not is_valid:
            if any("placeholder step" in str(e).lower() for e in (validation_errors or [])):
                raise ValueError(f"Ingestion blocked: Playbook failed validation: {validation_errors}")
            err_msg = f"Scenario 3/4 Validation Error (Attempt {attempt}): {validation_errors}"
            print(f"[JIT Converter Warning] Plan validation failed: {validation_errors}")
            feedback_history.append(f"- {err_msg}")
            continue

        print(f"[JIT Converter Auto-Retry] Conversion succeeded on Attempt {attempt}/{max_retries}!")
        break

    if not last_data or not last_is_valid:
        err_summary = "; ".join(str(e) for e in last_validation_errors) if last_validation_errors else "Validation failed"
        raise ValueError(f"Ingestion blocked: Playbook failed validation: {err_summary}")

    data = last_data
    is_valid = last_is_valid
    validation_errors = last_validation_errors

    sop_id_raw = data.get("sop_id") or ""
    clean_slug = re.sub(r"[^A-Za-z0-9]+", "-", raw_filename_base).strip("-").upper()
    clean_slug_truncated = clean_slug.replace("SOP-", "")[:20]
    derived_id = f"SOP-{clean_slug_truncated}"

    sop_id = override_sop_id or (derived_id if not sop_id_raw or "SOP-DYN-001" in sop_id_raw or "generate" in sop_id_raw.lower() else sop_id_raw)
    title = data.get("title", os.path.basename(raw_filepath))
    category = (data.get("category") or "other").lower().strip()
    target_os = data.get("target_os", "windows")
    description = data.get("description", f"Automated playbook for {title}.")
    # Genuine confidence derivation from converter or plan validator
    v_score = data.get("validation_confidence_score")
    c_score = data.get("confidence_score")
    if c_score is not None:
        confidence_score = float(c_score)
    elif v_score is not None:
        confidence_score = float(v_score)
    else:
        confidence_score = 0.50

    confidence_level = data.get("confidence_level") or data.get("validation_confidence_level")
    if not confidence_level:
        confidence_level = "High" if confidence_score >= 0.85 else ("Medium" if confidence_score >= 0.60 else "Low")

    confidence_reason = (
        data.get("confidence_reason")
        or data.get("validation_confidence_reason")
        or f"Confidence evaluated from step linkage and validation audit ({confidence_level})."
    )

    steps = data.get("steps", [])
    source_action_coverage = data.get("source_action_coverage") or []
    automation_status = data.get("automation_status") or "fully_automated"
    if any(item.get("coverage") == "unsupported_required" for item in source_action_coverage if isinstance(item, dict)):
        automation_status = "needs_review"

    # Parameter extraction from step commands and tool inputs (replacing hardcoded fallback)
    raw_req_entities = data.get("required_entities")
    if raw_req_entities is None:
        discovered_entities = set()
        for s in steps:
            cmd_str = f"{s.get('command', '')} {json.dumps(s.get('comm_inputs') or {})}"
            for match in re.findall(r"\{\{([A-Za-z0-9_]+)\}\}|<([A-Za-z0-9_]+)>|\$([A-Za-z0-9_]+)", cmd_str):
                var_name = next(v for v in match if v)
                if var_name.lower() not in ("true", "false", "null", "none", "null", "true", "false", "this", "it"):
                    discovered_entities.add(var_name.lower())
        raw_req_entities = list(discovered_entities)

    required_entities = list(dict.fromkeys([ENTITY_KEY_MAP.get(str(e).lower(), str(e)) for e in raw_req_entities]))
    trigger_words = data.get("trigger_words", [title])
    platform = data.get("platform")
    if not platform:
        for s in steps:
            if s.get("platform"):
                platform = s.get("platform")
                break
    platform = platform or "system"

    if platform and platform != "system" and platform.lower() not in [t.lower() for t in trigger_words]:
        trigger_words.insert(0, platform)

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
        "automation_status": automation_status,
        "required_entities": required_entities,
        "trigger_words": trigger_words,
        "steps": steps,
        "source_action_coverage": source_action_coverage,
        "document_metadata": data.get("document_metadata") or {},
    }

    return {
        "frontmatter": frontmatter_dict,
        "is_executable": True,
        "unexecutable_reason": None,
        "parser_type": parser_type,
        "raw_chars": len(raw_text),
        "reasoning_chain": [str(s) for s in (data.get("reasoning_chain") or [])],
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "confidence_reason": confidence_reason,
        "is_valid": is_valid,
        "validation_errors": validation_errors or [],
    }


def convert_raw_sop_to_okf(raw_filepath: str, override_sop_id: Optional[str] = None) -> Tuple[Optional[str], Dict[str, Any]]:
    """One-shot ingestion: parses raw SOP, plans OKF, and writes playbook to disk."""
    draft = plan_okf_from_raw(raw_filepath, override_sop_id=override_sop_id)
    if draft.get("is_executable") is False or draft.get("frontmatter", {}).get("is_executable") is False:
        unexec_reason = draft.get("unexecutable_reason") or draft.get("frontmatter", {}).get("unexecutable_reason") or "SOP is not actionable."
        metadata = dict(draft.get("frontmatter", {}))
        metadata["status"] = "unactionable"
        metadata["reason"] = unexec_reason
        return None, metadata

    if not draft.get("is_valid", False):
        err_details = draft.get("validation_errors", ["Plan validation failed"])
        raise ValueError(f"Ingestion blocked: Playbook failed validation: {err_details}")

    okf_file_path = write_okf_playbook(draft, raw_filename=os.path.basename(raw_filepath))
    return okf_file_path, draft["frontmatter"]


__all__ = [
    "plan_okf_from_raw",
    "convert_raw_sop_to_okf",
    "_log_converter_input",
]
