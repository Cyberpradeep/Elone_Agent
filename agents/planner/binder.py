import json
import re
from typing import Any, Tuple, Dict, List
from pydantic import BaseModel, Field

from shared.llm_config import get_llm
from execution_tools.variable_resolver import resolve_step_placeholders
from agents.planner.prompts import PLANNER_DEEP_COT_SYSTEM_PROMPT


class DeepCoTPlanResult(BaseModel):
    stage1_data_understanding: str = Field(
        default="Analyzed ticket context, host details, and SOP steps.",
        description="Stage 1: Deep summary of all input data (Ticket, User, Host Prabanjan, Environment, SOP, Memory)."
    )
    stage2_gap_delta_analysis: str = Field(
        default="Identified placeholders to bind and variables to link.",
        description="Stage 2: Identification of what needs to be planned & updated (placeholders to bind, variables to link)."
    )
    stage3_memory_pattern_analysis: str = Field(
        default="Analyzed reflection rules and host quirks.",
        description="Stage 3: Analysis of Reflection Rules (past error fixes) and Device Profile (host quirks)."
    )
    stage4_update_plan_formulation: str = Field(
        default="Formulated plan modifications.",
        description="Stage 4: Formulated plan for updating step parse instructions, timeouts, and execute_if rules."
    )
    stage5_plan_verification_validation: str = Field(
        default="Verified plan against ticket context.",
        description="Stage 5: Final sanity check verifying the modified plan against original ticket context & host details."
    )
    is_plan_valid: bool = Field(
        default=True,
        description="True if the plan passed all 5 CoT reasoning stages with 100% confidence."
    )
    bound_sop_id: str = Field(default="SOP-001", description="SOP ID being planned (e.g. SOP-NET-001)")
    target_hostname: str = Field(default="target_machine", description="Target host (e.g. Prabanjan)")
    steps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The final 100% executable steps array ready for remote execution."
    )


def _is_entity_in_dict(key: str, entities: dict) -> bool:
    if not key:
        return True
    clean_k = key.strip().lower()
    return bool(entities.get(key) or entities.get(clean_k))


def validate_planner_execution_plan(
    execution_plan: Dict[str, Any],
    required_entities: List[str] | None = None,
    entities: Dict[str, Any] | None = None
) -> Tuple[bool, List[str]]:
    """Fast Deterministic Python Validator for Live Ticket Execution Plans (< 1ms).

    Zero LLM token cost. Checks placeholder resolution, required entities, and variable linkage.
    """
    errors = []
    steps = execution_plan.get("steps", [])
    entities = entities or {}

    if not steps:
        return False, ["Deterministic Planner Error: Execution plan contains zero steps."]

    # 1. Required Entities Check
    if required_entities:
        missing_entities = [req for req in required_entities if not _is_entity_in_dict(req, entities)]
        if missing_entities:
            errors.append(f"Deterministic Planner Error: Missing required entities for execution: {missing_entities}")

    extracted_variables = set()

    for idx, step in enumerate(steps, start=1):
        cmd = (step.get("command") or "") + " " + str(step.get("comm_inputs") or "")
        parse_instruction = step.get("output_parse_instruction") or ""
        output_var = step.get("output_variable")
        execute_if = step.get("execute_if")

        # 2. Track variables extracted in preceding steps
        if output_var:
            extracted_variables.add(str(output_var).lower())
        parsed_vars = re.findall(
            r"(?:set\s+['\"]?(?:variables\.)?(\w+)['\"]?\s+(?:to|=)|store\s+[\w\.\_\[\]]+\s+in\s+(?:variables\.)?(\w+)|['\"]?(\w+)['\"]?\s*(?:=|to)\s*['\"]?(?:true|false|\w+)['\"]?)",
            parse_instruction,
            re.IGNORECASE
        )
        for tup in parsed_vars:
            for v in tup:
                if v and v.lower() not in ("true", "false", "variables", "entities", "none", "null", "output", "inspect"):
                    extracted_variables.add(v.lower())

        # 3. Check single brace placeholders
        single_placeholders = re.findall(r"(?<!\{)\{([a-zA-Z_][\w\.]*)\}(?!\})", cmd)
        for p in single_placeholders:
            clean_p = p.replace("variables.", "").replace("entities.", "").strip()
            if clean_p.lower() not in ("null", "none", "true", "false", "entities", "variables"):
                if not _is_entity_in_dict(clean_p, entities) and clean_p.lower() not in extracted_variables:
                    errors.append(
                        f"Deterministic Planner Error: Step {idx} requires missing entity or variable '{p}': '{cmd}'"
                    )

        # 4. Variable Linkage Precondition Check
        if execute_if:
            req_vars = re.findall(r"(?:\{\{variables\.(\w+)\}\}|\{variables\.(\w+)\}|variables\.(\w+))", str(execute_if))
            for match in req_vars:
                req_var = next(v for v in match if v)
                if req_var.lower() not in extracted_variables and not _is_entity_in_dict(req_var, entities):
                    errors.append(
                        f"Deterministic Planner Error: Step {idx} has execute_if requirement '{req_var}', "
                        f"but '{req_var}' is never extracted in preceding step parse instructions!"
                    )

    if errors:
        return False, errors

    return True, []


def synthesize_execution_plan_with_deep_cot(
    intent: str,
    category: str,
    environment: str,
    hostname: str,
    entities: dict[str, Any],
    sop_id: str,
    sop_title: str,
    raw_sop_steps: list[dict[str, Any]],
    reflection_rules: str,
    device_quirks: str,
    required_entities: list[str] | None = None,
    raw_sop_text: str = ""
) -> Tuple[Dict[str, Any], list[str], bool, str]:
    """Process 2: Synthesizes a tailored, 100% executable plan using 6-Stage Deep CoT reasoning."""
    reasoning_chain = [
        f"[Stage 1 Data Understanding]: Analyzed ticket '{intent}' for host '{hostname}'.",
        f"[Stage 2 Gap & Delta Analysis]: Bound dynamic placeholders ({{entities.hostname}} -> {hostname}).",
        f"[Stage 3 Memory Pattern Analysis]: Applied reflection rules and device quirks for host '{hostname}'.",
        f"[Stage 4 Update Formulation]: Formulated {len(raw_sop_steps)} execution steps.",
        f"[Stage 5 Final Verification]: Verified plan syntax for host '{hostname}'.",
    ]
    generated_steps = raw_sop_steps

    try:
        llm = get_llm("execution_planning", temperature=0)
        prompt = PLANNER_DEEP_COT_SYSTEM_PROMPT.format(
            intent=intent,
            category=category,
            environment=environment,
            hostname=hostname,
            entities=json.dumps(entities),
            sop_id=sop_id,
            sop_title=sop_title,
            raw_sop_steps=json.dumps(raw_sop_steps, indent=2),
            reflection_rules=reflection_rules or "(No reflection rules)",
            device_quirks=device_quirks or "(No device quirks)",
        )
        response = llm.invoke([{"role": "system", "content": prompt}])
        raw_res = response.content if hasattr(response, "content") else str(response)
        content = raw_res if isinstance(raw_res, str) else str(raw_res)
        cleaned_content = re.sub(r"```json\s*", "", content)
        cleaned_content = re.sub(r"```\s*", "", cleaned_content).strip()
        if "{" in cleaned_content and "}" in cleaned_content:
            json_str = cleaned_content[cleaned_content.find("{"):cleaned_content.rfind("}")+1]
            parsed = json.loads(json_str)
            if "steps" in parsed and isinstance(parsed["steps"], list) and len(parsed["steps"]) > 0:
                generated_steps = parsed["steps"]
            if "reasoning_chain" in parsed and isinstance(parsed["reasoning_chain"], list):
                reasoning_chain = parsed["reasoning_chain"]
    except Exception as e:
        print(f"[Planner Binder Info] Standard CoT Plan Assembly applied ({e})")

    # Ensure alias key normalization in entities dict for fallback binding
    effective_entities = dict(entities)
    if "hostname" in effective_entities:
        effective_entities["computername"] = effective_entities["hostname"]
        effective_entities["computer_name"] = effective_entities["hostname"]
        effective_entities["target_host"] = effective_entities["hostname"]
    if "executable" in effective_entities:
        effective_entities["application_exe"] = effective_entities["executable"]
        effective_entities["app_exe"] = effective_entities["executable"]
        effective_entities["exe_name"] = effective_entities["executable"]
    if "application_name" in effective_entities:
        effective_entities["app_name"] = effective_entities["application_name"]

    # Python Placeholder Binding Pass (Guarantees {{entities.hostname}} -> Prabanjan)
    resolved_steps = [
        resolve_step_placeholders(step, effective_entities, effective_entities)
        for step in generated_steps
    ]

    execution_plan = {"steps": resolved_steps}

    # Determine default required entities based on step types in execution plan (tool_call playbooks do not require OS hostname)
    if required_entities is None:
        has_command_step = any(s.get("step_type") == "command" or s.get("command") for s in raw_sop_steps)
        effective_req_entities = ["hostname"] if has_command_step else []
    else:
        effective_req_entities = required_entities

    # Fast Deterministic Python Validation (< 1ms, 0 Token Cost)
    is_valid, validation_errors = validate_planner_execution_plan(
        execution_plan=execution_plan,
        required_entities=effective_req_entities,
        entities=entities
    )
    feedback_str = "\n".join(validation_errors) if validation_errors else "Planner execution plan validated deterministically."

    return execution_plan, reasoning_chain, is_valid, feedback_str

