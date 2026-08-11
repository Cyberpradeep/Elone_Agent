"""Fast JSON response parsing and variable extraction logic for Execution Result Agent."""

import json
import re
from typing import Tuple, Dict, Any

from .llm import run_result_analysis


def _lookup_json_path(data: Any, path: str) -> Any:
    """Navigates dot/index notation like 'users[0].id' or 'users.0.id' in parsed JSON."""
    if not path or not data:
        return None
    # Strip prefixes like response., success.
    clean_path = re.sub(r"^(?:response\.)?(?:success\.)?", "", path.strip())
    # Convert brackets to dot notation: users[0].id -> users.0.id
    normalized_path = re.sub(r"\[(\d+)\]", r".\1", clean_path)
    parts = normalized_path.split(".")
    curr = data

    for p in parts:
        if isinstance(curr, dict):
            if p in curr:
                curr = curr[p]
            else:
                return None
        elif isinstance(curr, list):
            try:
                idx = int(p)
                if 0 <= idx < len(curr):
                    curr = curr[idx]
                else:
                    return None
            except ValueError:
                return None
        else:
            return None
    return curr


def _extract_structural_json_vars(parsed_json: Dict[str, Any]) -> Dict[str, Any]:
    """Pure structural JSON data extraction via native dictionary lookups (< 1ms).

    Zero text regex matching. Directly extracts scalar keys, status fields, and nested array properties.
    """
    ext_vars = {}

    # 1. Top-level primitive keys
    for k, v in parsed_json.items():
        clean_k = k.replace("entities.", "").replace("variables.", "").strip("{}")
        if not isinstance(v, (dict, list)):
            ext_vars[clean_k] = str(v)

    # 2. Extract nested array properties (e.g. users[0].id)
    for list_key in ("users", "items", "data", "accounts", "results"):
        arr = parsed_json.get(list_key)
        if isinstance(arr, list) and len(arr) > 0:
            ext_vars["account_found"] = "true"
            if isinstance(arr[0], dict):
                first_item = arr[0]
                if "id" in first_item:
                    ext_vars["user_id"] = str(first_item["id"])
                    ext_vars["id"] = str(first_item["id"])
                for fk, fv in first_item.items():
                    if not isinstance(fv, (dict, list)):
                        clean_fk = fk.replace("entities.", "").replace("variables.", "").strip("{}")
                        ext_vars[clean_fk] = str(fv)
        elif isinstance(arr, list) and len(arr) == 0:
            ext_vars["account_found"] = "false"

    if parsed_json.get("found") is True or str(parsed_json.get("found")).lower() == "true":
        ext_vars["account_found"] = "true"

    return ext_vars


def extract_variables_and_verdict(
    target_step: Dict[str, Any],
    step_num: int,
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    hostname: str,
    variables: Dict[str, Any]
) -> Tuple[Dict[str, Any], str, str]:
    """Parses execution output and determines next_action verdict & extracted variables.

    - For API Tool Calls / JSON stdout: Performs fast structural JSON extraction (< 1ms).
    - For steps with output_parse_instruction: Invokes LLM reasoning pass to evaluate conditional rules accurately.

    Returns: (normalized_extracted_vars, next_action, reasoning)
    """
    step_type = target_step.get("step_type", "command")
    parse_instr = target_step.get("output_parse_instruction") or ""

    # 1. Fast Deterministic Structural JSON Parsing
    if step_type in ("tool_call", "verification", "condition") or (stdout and stdout.strip().startswith("{") and stdout.strip().endswith("}")):
        try:
            parsed_json = json.loads(stdout)
            if isinstance(parsed_json, dict):
                print(f"  [Execution Result Fast Parser] Parsed API/Verification Response JSON in < 1ms.")
                ext_vars = _extract_structural_json_vars(parsed_json)

                # Detect API error responses
                is_error = (
                    "error" in parsed_json or
                    parsed_json.get("status") in ("error", "failed") or
                    (isinstance(parsed_json.get("code"), int) and parsed_json.get("code") >= 400)
                )

                # Ensure output_variable is set if requested (only on success)
                out_var = target_step.get("output_variable")
                if not is_error and out_var and out_var not in ext_vars:
                    ext_vars[out_var] = "success"

                verdict = "RETRY" if is_error else ("SUCCESS" if exit_code == 0 else "RETRY")
                status_desc = parsed_json.get("error") if is_error else parsed_json.get("status", "success")
                reasoning = f"Fast JSON Response Parsed: status={status_desc}"

                # If output_parse_instruction contains conditional instructions, invoke LLM CoT reasoning
                if parse_instr and ("if" in parse_instr.lower() or "set" in parse_instr.lower() or "store" in parse_instr.lower()):
                    try:
                        analysis = run_result_analysis(
                            hostname=hostname,
                            step_num=step_num,
                            target_step=target_step,
                            command=command,
                            stdout=stdout,
                            stderr=stderr,
                            exit_code=exit_code,
                            variables={**variables, **ext_vars}
                        )
                        raw_llm_vars = getattr(analysis, "extracted_variables", None) or []
                        if isinstance(raw_llm_vars, list):
                            for item in raw_llm_vars:
                                k = getattr(item, "key", None) or (item.get("key") if isinstance(item, dict) else None)
                                v = getattr(item, "value", None) or (item.get("value") if isinstance(item, dict) else None)
                                if k and v is not None:
                                    clean_k = k.replace("entities.", "").replace("variables.", "").strip("{}")
                                    val_str = str(v)
                                    if val_str.lower() in ("true", "1"):
                                        val_str = "true"
                                    elif val_str.lower() in ("false", "0"):
                                        val_str = "false"
                                    ext_vars[clean_k] = val_str
                        elif isinstance(raw_llm_vars, dict):
                            for k, v in raw_llm_vars.items():
                                clean_k = k.replace("entities.", "").replace("variables.", "").strip("{}")
                                val_str = str(v)
                                if val_str.lower() in ("true", "1"):
                                    val_str = "true"
                                elif val_str.lower() in ("false", "0"):
                                    val_str = "false"
                                ext_vars[clean_k] = val_str
                        if hasattr(analysis, "next_action") and getattr(analysis, "next_action"):
                            verdict = getattr(analysis, "next_action")
                        reasoning += f" | LLM Instruction Reasoning: {getattr(analysis, 'reasoning', '')}"
                    except Exception as llm_err:
                        print(f"  [Execution Result Info] LLM instruction evaluation fallback: {llm_err}")

                return ext_vars, verdict, reasoning

        except Exception as e:
            print(f"  [Execution Result Fast Parser Info] JSON parsing fallback to LLM: {e}")

    # 2. Direct LLM CoT Verification for All Step Execution Outputs

    analysis = run_result_analysis(
        hostname=hostname,
        step_num=step_num,
        target_step=target_step,
        command=command,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        variables=variables
    )

    next_act = getattr(analysis, "next_action", "SUCCESS" if exit_code == 0 else "RETRY")
    reasoning_text = getattr(analysis, "reasoning", f"Exit code {exit_code}")
    raw_ext_vars = getattr(analysis, "extracted_variables", None) or []

    # Normalize variable keys & boolean string representations (supports list[VariableEntry] or dict)
    normalized_vars = {}
    if isinstance(raw_ext_vars, list):
        for item in raw_ext_vars:
            k = getattr(item, "key", None) or (item.get("key") if isinstance(item, dict) else None)
            v = getattr(item, "value", None) or (item.get("value") if isinstance(item, dict) else None)
            if k is not None and v is not None:
                clean_key = str(k).replace("entities.", "").replace("variables.", "").strip("{}")
                val_str = str(v)
                if val_str.lower() in ("true", "1"):
                    val_str = "true"
                elif val_str.lower() in ("false", "0"):
                    val_str = "false"
                normalized_vars[clean_key] = val_str
    elif isinstance(raw_ext_vars, dict):
        for k, v in raw_ext_vars.items():
            clean_key = str(k).replace("entities.", "").replace("variables.", "").strip("{}")
            val_str = str(v)
            if val_str.lower() in ("true", "1"):
                val_str = "true"
            elif val_str.lower() in ("false", "0"):
                val_str = "false"
            normalized_vars[clean_key] = val_str




    # Guardrail Override for missing required output_variable
    req_output_var = target_step.get("output_variable")
    if next_act == "SUCCESS" and req_output_var and req_output_var not in normalized_vars:
        next_act = "RETRY"
        reasoning_text += f" [Guardrail Override: Required output variable '{req_output_var}' missing from extracted variables. Setting RETRY.]"
        print(f"  [Guardrail Warning] Required output variable '{req_output_var}' missing. Overriding verdict to RETRY.")

    return normalized_vars, next_act, reasoning_text
