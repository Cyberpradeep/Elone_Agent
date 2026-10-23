import json
import re
from typing import Any, Dict


def resolve_template_variables(text: str, entities: Dict[str, Any] = None, variables: Dict[str, Any] = None) -> str:
    """Replaces {{entities.key}}, {{variables.key}}, and single-brace placeholders deterministically in text.

    Performs direct key lookups across variables and entities scopes.
    Static entity placeholder binding is performed by the Planner Agent LLM during plan synthesis.
    """
    if not text or not isinstance(text, str):
        return text

    entities = entities or {}
    variables = variables or {}

    # 1. Replace {{entities.key}}
    def replace_entity(match):
        key = match.group(1).strip()
        val = entities.get(key) or variables.get(key)
        if val is None and key.lower() in ("application", "app", "executable", "app_exe"):
            val = entities.get("executable") or entities.get("application_name") or variables.get("executable")
        if val is not None:
            return str(val)
        return match.group(0)

    resolved_text = re.sub(r"\{+entities\.(.*?)\}+", replace_entity, text)

    # 2. Replace {{variables.path}}
    def replace_variable(match):
        raw_path = match.group(1).strip()
        parts = raw_path.split(".")
        current = variables

        for part in parts:
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    current = None
                    break
            else:
                current = None
                break

        if current is None and raw_path in entities:
            current = entities[raw_path]

        if current is not None and not isinstance(current, (dict, list)):
            return str(current)
        elif isinstance(current, (dict, list)):
            return json.dumps(current)
        
        return match.group(0)

    resolved_text = re.sub(r"\{+variables\.(.*?)\}+", replace_variable, resolved_text)

    # 3. Replace single-brace {key} placeholders (e.g. {user_id} or {variables.default_gateway_ip})
    def replace_single_brace(match):
        raw_key = match.group(1).strip()
        start = match.start()
        if start > 0 and resolved_text[start - 1] == '{':
            return match.group(0)

        if raw_key.startswith("variables."):
            clean_key = raw_key[10:].strip()
            val = variables.get(clean_key)
            if val is None:
                val = entities.get(clean_key)
            if val is not None:
                return str(val)
            return match.group(0)

        if raw_key.startswith("entities."):
            clean_key = raw_key[9:].strip()
            val = entities.get(clean_key)
            if val is None and clean_key.lower() in ("application", "app", "executable", "app_exe"):
                val = entities.get("executable") or entities.get("application_name")
            if val is not None:
                return str(val)
            return match.group(0)

        # Unadorned {key}: Check variables first, then entities
        val = entities.get(raw_key) or variables.get(raw_key)
        if val is None and raw_key.lower() in ("application", "app", "executable", "app_exe"):
            val = entities.get("executable") or entities.get("application_name")
        if val is not None:
            return str(val)

        return match.group(0)

    resolved_text = re.sub(r"(?<!\{)\{([\w\.]+)\}(?!\})", replace_single_brace, resolved_text)
    # Deduplicate accidental double extension (e.g., Code.exe.exe -> Code.exe)
    resolved_text = re.sub(r"(\.exe)+\.exe\b", ".exe", resolved_text, flags=re.IGNORECASE)
    return resolved_text


def resolve_step_placeholders(step: dict, entities: dict = None, variables: dict = None) -> dict:
    """Creates a deep copy of a plan step dictionary with all string fields resolved."""
    step_copy = dict(step)
    entities = entities or {}
    variables = variables or {}

    for field in ["command", "fallback_command", "execute_if", "output_parse_instruction", "parse_instruction", "sop_step_description", "danger_warning"]:
        if field in step_copy and isinstance(step_copy[field], str):
            step_copy[field] = resolve_template_variables(step_copy[field], entities, variables)

    # Sync parse_instruction and output_parse_instruction
    p_instr = step_copy.get("output_parse_instruction") or step_copy.get("parse_instruction")
    if p_instr:
        step_copy["output_parse_instruction"] = p_instr
        step_copy["parse_instruction"] = p_instr

    if "comm_inputs" in step_copy and isinstance(step_copy["comm_inputs"], dict):
        resolved_inputs = {}
        for k, v in step_copy["comm_inputs"].items():
            if isinstance(v, str):
                resolved_inputs[k] = resolve_template_variables(v, entities, variables)
            else:
                resolved_inputs[k] = v
        step_copy["comm_inputs"] = resolved_inputs

    return step_copy
