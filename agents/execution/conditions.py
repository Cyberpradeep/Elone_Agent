"""Precondition evaluation logic for Execution Agent."""

import re
from typing import Dict, Any


def evaluate_condition(cond_str: str, entities: Dict[str, Any] = None, variables: Dict[str, Any] = None) -> bool:
    """Safely parses and evaluates string conditions like:
    - 'variables.ifeo_key_exists == true' or '{{variables.dhcp_failure}} == true'
    """
    if not cond_str or cond_str.strip() == "" or cond_str.strip().lower() == "none":
        return True

    entities = entities or {}
    variables = variables or {}

    cond = cond_str.strip().lower()
    cond = cond.replace("&&", " and ").replace("||", " or ")

    def eval_simple_comparison(left: str, op: str, right: str) -> bool:
        left = left.strip().strip("'\"")
        right = right.strip().strip("'\"")

        clean_left = left.replace("variables.", "").replace("entities.", "").strip()
        synonyms = {
            "computer_name": "hostname",
            "target_host": "hostname",
            "application_exe_name": "executable",
            "app_exe": "executable",
        }
        resolved_left_key = synonyms.get(clean_left.lower(), clean_left)

        if clean_left in variables:
            left = str(variables[clean_left])
        elif clean_left in entities:
            left = str(entities[clean_left])
        elif resolved_left_key in variables:
            left = str(variables[resolved_left_key])
        elif resolved_left_key in entities:
            left = str(entities[resolved_left_key])

        def normalize_val(val: str):
            if val in ("true", "1"):
                return True
            if val in ("false", "0"):
                return False
            if val in ("null", "none"):
                return None
            if val.isdigit():
                return int(val)
            return val

        left_val = normalize_val(left)
        right_val = normalize_val(right)

        if op == "==":
            return left_val == right_val
        elif op == "!=":
            return left_val != right_val
        return False

    parts = re.split(r"\s+(and|or)\s+", cond)
    results = []
    operators = []

    for part in parts:
        part = part.strip()
        if part in ("and", "or"):
            operators.append(part)
        else:
            comp_match = re.match(r"^(.*?)\s*(==|!=)\s*(.*?)$", part)
            if comp_match:
                l, op, r = comp_match.groups()
                results.append(eval_simple_comparison(l, op, r))
            else:
                part_clean = part.strip("'\"")
                if part_clean in ("true", "1"):
                    results.append(True)
                elif part_clean in ("false", "null", "none", "0", ""):
                    results.append(False)
                else:
                    results.append(bool(part_clean))

    if not results:
        return True

    final_res = results[0]
    for i, op in enumerate(operators):
        if i + 1 < len(results):
            next_val = results[i + 1]
            if op == "and":
                final_res = final_res and next_val
            elif op == "or":
                final_res = final_res or next_val
    return final_res
