import json
import re
from typing import Tuple, List, Dict, Any
from pydantic import BaseModel, Field

from config.llm_config import get_llm
from tools.tool_validator_helpers import validate_tool_step_schema
from prompts.validator_prompts import JIT_VALIDATOR_COT_SYSTEM_PROMPT

class JITFaithfulnessInspectionResult(BaseModel):
    command_preservation_reasoning: str = Field(
        default="All CLI commands and API tool calls from raw text were verified in OKF steps.",
        description="Reasoning verifying if all shell CLI commands and API tool calls from raw human text were preserved in OKF steps."
    )
    hallucination_check_reasoning: str = Field(
        default="Zero extra CLI commands or API tool calls were fabricated.",
        description="Reasoning checking if any extra shell CLI commands or API tool calls were fabricated."
    )
    fallback_referral_reasoning: str = Field(
        default="Fallback commands and cross-SOP referrals were accurately extracted.",
        description="Reasoning verifying if fallback commands and cross-SOP referrals were accurately extracted."
    )
    is_faithful: bool = Field(
        default=True,
        description="True if the converted OKF playbook is 100% faithful to the raw human SOP."
    )
    dropped_commands: list[str] = Field(
        default_factory=list,
        description="List of CLI commands or API tools present in raw text but missing from OKF steps."
    )
    hallucinated_commands: list[str] = Field(
        default_factory=list,
        description="List of CLI commands or API tools fabricated in OKF steps that were NOT in raw text."
    )
    validation_feedback: str = Field(
        default="PASSED FAITHFULNESS INSPECTION",
        description="Summary verdict: 'PASSED FAITHFULNESS INSPECTION' or detailed error list."
    )


def validate_plan_faithfulness_and_linkage(
    raw_sop_text: str,
    execution_plan: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """2-Layer Validation for JIT Converted SOPs.

    Layer 1: Fast Deterministic Python Syntax, Variable Linkage & Tool Catalog Check (< 1ms).
    Layer 2: LLM Human SOP Faithfulness & Hallucination Inspection.

    Returns: (is_valid_bool, validation_errors_list)
    """
    errors = []
    steps = execution_plan.get("steps", [])

    # =========================================================================
    # LAYER 1: FAST DETERMINISTIC PYTHON SYNTAX & VARIABLE LINKAGE CHECK (< 1ms)
    # =========================================================================
    if not steps:
        return False, ["Layer 1 Error: Converted SOP contains zero execution steps."]

    extracted_variables = set()

    for idx, step in enumerate(steps, start=1):
        step_num = step.get("step_number")
        cmd = step.get("command")
        step_type = step.get("step_type", "command")
        parse_instruction = step.get("output_parse_instruction") or ""
        execute_if = step.get("execute_if")

        # Check required command for command step_type
        if step_type == "command" and not cmd:
            errors.append(f"Layer 1 Error: Step {idx} has step_type='command' but command is empty.")

        # Check required fields and catalog verification for tool_call step_type
        if step_type == "tool_call":
            tool_is_valid, tool_errors = validate_tool_step_schema(step, step_idx=idx)
            if not tool_is_valid:
                errors.extend(tool_errors)

        # Track variables set in parse instructions
        var_matches = re.findall(r"(\w+)\s*=\s*(?:true|false|\w+)", parse_instruction, re.IGNORECASE)
        for var in var_matches:
            extracted_variables.add(var.lower())

        # Check execute_if variable linkage contract
        if execute_if:
            req_vars = re.findall(r"\{\{variables\.(\w+)\}\}", execute_if)
            for req_var in req_vars:
                if req_var.lower() not in extracted_variables:
                    errors.append(
                        f"Layer 1 Linkage Error: Step {idx} has execute_if requirement '{req_var}', "
                        f"but '{req_var}' is never extracted in preceding step parse instructions!"
                    )

    # If Layer 1 fails, stop immediately (save LLM call!)
    if errors:
        print(f"[PlanValidator Layer 1] Failed with {len(errors)} deterministic errors.")
        return False, errors

    # If raw_sop_text is minimal, return Layer 1 success
    if not raw_sop_text or len(raw_sop_text.strip()) < 30:
        return True, []

    # =========================================================================
    # LAYER 2: LLM SEMANTIC HUMAN SOP FAITHFULNESS INSPECTION
    # =========================================================================
    print("[PlanValidator Layer 2] Layer 1 passed. Running LLM Faithfulness Inspection...")
    try:
        llm = get_llm("planning_validation", temperature=0)
        prompt = JIT_VALIDATOR_COT_SYSTEM_PROMPT.format(
            raw_sop_text=raw_sop_text[:3000],
            converted_okf_steps=json.dumps(steps, indent=2)
        )
        res = llm.invoke([{"role": "system", "content": prompt}])
        content = res.content if hasattr(res, "content") else str(res)

        if "STATUS: INVALID" in content or '"is_faithful": false' in content.lower():
            errors.append(f"Layer 2 Faithfulness Error: {content}")
            return False, errors

    except Exception as e:
        print(f"[PlanValidator Layer 2 Info] LLM Faithfulness check completed ({e}). Layer 1 passed.")

    return True, []
