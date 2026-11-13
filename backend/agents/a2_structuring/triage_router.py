"""
Agent A2: Triage Router
=======================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.2)
Stage 1: Dynamic Tool-Aware Intent Classifier & Router.
Classifies unstructured SOP into 'command', 'tool_call', 'hybrid', or 'unactionable'.
"""

import os
import re
import json
import time
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, ToolMessage
from utils.cancellation import check_cancelled
try:
    from utils.security import escape_prompt_delimiters
except ImportError:
    from backend.utils.security import escape_prompt_delimiters

# pyrefly: ignore [missing-import]
from config.llm_config import get_llm, resolve_llm_metadata
# pyrefly: ignore [missing-import]
from tools.tool_functions import DYNAMIC_CATALOG_TOOLS
# pyrefly: ignore [missing-import]
from prompts.jit_converter_prompts import TRIAGE_ROUTER_PROMPT
try:
    from utils.pipeline_logger import log_info, log_warning, log_triage_result
except ImportError:
    from backend.utils.pipeline_logger import log_info, log_warning, log_triage_result


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


ENABLE_TOOL_INSPECTION_DEFAULT = os.getenv("ELONE_ENABLE_TOOL_INSPECTION", "1").lower() in ("1", "true", "yes")
_VALID_CONF_LEVELS = {"L0", "L1", "L2", "L3"}


def _sanitize_confidentiality_advisory(raw: Any) -> Dict[str, Any]:
    """Normalizes optional LLM confidentiality advisory block for Agent A3."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {
        "security_controls": raw.get("security_controls") is True,
        "customer_data": raw.get("customer_data") is True,
        "legal_financial": raw.get("legal_financial") is True,
        "proprietary_process": raw.get("proprietary_process") is True,
    }
    lvl = str(raw.get("suggested_level") or "").strip().upper()
    if lvl in _VALID_CONF_LEVELS:
        out["suggested_level"] = lvl
    rationale = str(raw.get("rationale") or "").strip()
    if rationale:
        out["rationale"] = rationale[:240]
    return out


def run_triage_router(
    enriched_sop_text: str,
    sop_slug: str,
    override_sop_id: Optional[str] = None,
    enable_tool_inspection: Optional[bool] = None,
) -> Dict[str, Any]:
    """Stage 1: Intent Classifier & Router.
    - Default (Fast path): 1-turn direct LLM evaluation for command-based SOPs and prompt-injection detection.
    - Future-ready (enable_tool_inspection=True or ELONE_ENABLE_TOOL_INSPECTION=1): Dynamic multi-turn SaaS tool catalog discovery.
    """
    if enable_tool_inspection is None:
        enable_tool_inspection = ENABLE_TOOL_INSPECTION_DEFAULT

    log_info("Triage Router", f"Analyzing execution paradigm (tool_inspection={'enabled' if enable_tool_inspection else 'fast-path'})...")
    try:
        from tools.platforms import get_dynamic_catalog_summary
        catalog_summary = get_dynamic_catalog_summary()
    except Exception:
        try:
            from backend.tools.platforms import get_dynamic_catalog_summary
            catalog_summary = get_dynamic_catalog_summary()
        except Exception:
            catalog_summary = []

    catalog_text = json.dumps(catalog_summary, indent=2) if catalog_summary else "No platforms registered."
    safe_raw_sop = escape_prompt_delimiters((enriched_sop_text or "")[:5000])
    triage_replacements = {
        "{registered_platforms_catalog}": catalog_text,
        "{raw_sop_text}": safe_raw_sop,
    }
    triage_placeholder_re = re.compile("|".join(re.escape(k) for k in triage_replacements))
    triage_prompt = triage_placeholder_re.sub(
        lambda m: triage_replacements[m.group(0)],
        TRIAGE_ROUTER_PROMPT,
    )
    llm = get_llm("execution_planning", temperature=0.0)
    messages = [HumanMessage(content=triage_prompt)]
    content = ""

    def _enforce_daily_quota() -> None:
        try:
            from gemini_monitor.monitor import check_daily_limit
            check_daily_limit("gemini")
        except Exception as q_err:
            if "Quota" in type(q_err).__name__ or "DailyQuotaExceededError" in str(type(q_err)):
                raise

    trace_id_val = override_sop_id or sop_slug
    prov, mdl = resolve_llm_metadata(llm, "execution_planning")

    if not enable_tool_inspection:
        # Fast path for command-based SOPs: 1 single direct LLM evaluation without tool loop latency
        _enforce_daily_quota()
        check_cancelled()
        t0 = time.perf_counter()
        try:
            res = llm.invoke(messages)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        except Exception as inv_err:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            try:
                from gemini_monitor.monitor import record_call
                record_call(
                    caller="triage_router",
                    model=mdl,
                    provider=prov,
                    input_tokens=0,
                    output_tokens=0,
                    sop_id=trace_id_val,
                    trace_id=trace_id_val,
                    latency_ms=latency_ms,
                    status="error",
                    error_message=str(inv_err),
                )
            except Exception:
                pass
            raise inv_err

        in_tok = getattr(res, "usage_metadata", {}).get("input_tokens", 0) if hasattr(res, "usage_metadata") and res.usage_metadata else 0
        out_tok = getattr(res, "usage_metadata", {}).get("output_tokens", 0) if hasattr(res, "usage_metadata") and res.usage_metadata else 0
        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import record_call
            record_call(
                caller="triage_router",
                model=mdl,
                provider=prov,
                input_tokens=in_tok,
                output_tokens=out_tok,
                sop_id=trace_id_val,
                trace_id=trace_id_val,
                latency_ms=latency_ms,
                status="success",
            )
        except Exception as e:
            log_warning("Gemini Monitor", f"Failed to log triage call: {e}")

        raw_c = res.content if hasattr(res, "content") else str(res)
        if isinstance(raw_c, list):
            raw_c = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c])
        content = raw_c
    else:
        # Full dynamic platform tool-calling loop (Easily wired when adding SaaS platforms)
        tool_map = {t.name: t for t in DYNAMIC_CATALOG_TOOLS}
        llm_with_tools = llm.bind_tools(DYNAMIC_CATALOG_TOOLS)
        max_tool_turns = 6

        for turn in range(max_tool_turns):
            _enforce_daily_quota()
            check_cancelled()
            t0 = time.perf_counter()
            try:
                res = llm_with_tools.invoke(messages)
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            except Exception as invoke_err:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                try:
                    from gemini_monitor.monitor import record_call
                    record_call(
                        caller="triage_router",
                        model=mdl,
                        provider=prov,
                        input_tokens=0,
                        output_tokens=0,
                        sop_id=trace_id_val,
                        trace_id=trace_id_val,
                        latency_ms=latency_ms,
                        status="error",
                        error_message=str(invoke_err),
                    )
                except Exception:
                    pass

                log_warning("Triage Router", f"Tool invocation error ({invoke_err}). Falling back to direct evaluation without tools...")
                fallback_prompt = (
                    "Tool inspection phase complete or encountered an API error. "
                    "Analyze the SOP directly using known IT platform capabilities and classify into "
                    "'command', 'tool_call', 'hybrid', or 'unactionable'. Output the final triage JSON now."
                )
                try:
                    _enforce_daily_quota()
                    t0_fb = time.perf_counter()
                    fallback_res = llm.invoke(messages + [HumanMessage(content=fallback_prompt)])
                    fb_latency_ms = round((time.perf_counter() - t0_fb) * 1000, 2)
                    fb_in_tok = getattr(fallback_res, "usage_metadata", {}).get("input_tokens", 0) if hasattr(fallback_res, "usage_metadata") and fallback_res.usage_metadata else 0
                    fb_out_tok = getattr(fallback_res, "usage_metadata", {}).get("output_tokens", 0) if hasattr(fallback_res, "usage_metadata") and fallback_res.usage_metadata else 0
                    try:
                        from gemini_monitor.monitor import record_call
                        record_call(
                            caller="triage_router",
                            model=mdl,
                            provider=prov,
                            input_tokens=fb_in_tok,
                            output_tokens=fb_out_tok,
                            sop_id=trace_id_val,
                            trace_id=trace_id_val,
                            latency_ms=fb_latency_ms,
                            status="success",
                        )
                    except Exception:
                        pass
                    raw_c = fallback_res.content if hasattr(fallback_res, "content") else str(fallback_res)
                    if isinstance(raw_c, list):
                        content = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c])
                    else:
                        content = str(raw_c)
                except Exception as fb_err:
                    log_warning("Triage Router", f"Direct evaluation fallback failed: {fb_err}")
                break

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
                    model=mdl,
                    provider=prov,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    sop_id=trace_id_val,
                    trace_id=trace_id_val,
                    latency_ms=latency_ms,
                    status="success",
                )
            except Exception as e:
                log_warning("Gemini Monitor", f"Failed to log triage call: {e}")

            if hasattr(res, "tool_calls") and res.tool_calls:
                messages.append(res)
                for tc in res.tool_calls:
                    t_name = tc["name"]
                    t_args = tc.get("args", {})
                    log_info("Triage Tool Inspection", f"Calling tool '{t_name}' with args: {t_args}...")
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

        if not content.strip():
            try:
                _enforce_daily_quota()
                check_cancelled()
                final_res = llm.invoke(messages + [HumanMessage(content="Tool inspection complete. Output the final triage JSON now.")])
                raw_c = final_res.content if hasattr(final_res, "content") else str(final_res)
                if isinstance(raw_c, list):
                    raw_c = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_c])
                content = str(raw_c)
            except Exception:
                pass

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

        log_triage_result(classification, conf_score, conf_level, is_exec, conf_reason, triage_data.get("triage_summary", "N/A"))
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
            "confidentiality_advisory": _sanitize_confidentiality_advisory(triage_data.get("confidentiality_advisory")),
        }
    except Exception as e:
        log_warning("Triage Router", f"Fallback parsing to 'command': {e}")
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
            "confidentiality_advisory": {},
        }


# Backwards compatibility alias
_run_triage_router = run_triage_router

__all__ = [
    "run_triage_router",
    "_run_triage_router",
    "ENTITY_KEY_MAP",
]
