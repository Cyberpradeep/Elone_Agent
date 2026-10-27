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
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, ToolMessage

# pyrefly: ignore [missing-import]
from config.llm_config import get_llm
# pyrefly: ignore [missing-import]
from tools.tool_functions import DYNAMIC_CATALOG_TOOLS
# pyrefly: ignore [missing-import]
from prompts.jit_converter_prompts import TRIAGE_ROUTER_PROMPT


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


def run_triage_router(
    enriched_sop_text: str,
    sop_slug: str,
    override_sop_id: Optional[str] = None,
) -> Dict[str, Any]:
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


# Backwards compatibility alias
_run_triage_router = run_triage_router

__all__ = [
    "run_triage_router",
    "_run_triage_router",
    "ENTITY_KEY_MAP",
]
