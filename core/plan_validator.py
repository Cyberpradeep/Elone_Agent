import json
import re
from typing import Tuple, List, Dict, Any
from pydantic import BaseModel, Field

# pyrefly: ignore [missing-import]
from config.llm_config import get_llm
# pyrefly: ignore [missing-import]
from tools.tool_validator_helpers import validate_tool_step_schema
# pyrefly: ignore [missing-import]
from tools.platforms import find_platform_schema
# pyrefly: ignore [missing-import]
from prompts.validator_prompts import JIT_VALIDATOR_COT_SYSTEM_PROMPT
# pyrefly: ignore [missing-import]
from schemas import JITFaithfulnessInspectionResult


# Deterministic High-Risk Security / Prompt Injection Command Patterns
MALICIOUS_COMMAND_PATTERNS = [
    (r"(?:powershell|pwsh).*(?:-enc|-encodedcommand)\s+[A-Za-z0-9+/=]{10,}", "Encoded PowerShell payload execution"),
    (r"(?:invoke-expression|iex)\s*[\(\$]", "Arbitrary script evaluation (Invoke-Expression / IEX)"),
    (r"certutil(?:\.exe)?\s+-(?:urlcache|decode|decodehex)", "Certutil binary download/decode exploitation"),
    (r"bitsadmin(?:\.exe)?\s+/transfer", "Bitsadmin background downloader"),
    (r"net\s+user\s+[^/\s]+\s+[^/\s]+\s+/add", "Unauthorized backdoor local user creation (net user /add)"),
    (r"net\s+localgroup\s+administrators\s+[^/\s]+\s+/add", "Privilege escalation to local administrator"),
    (r"(?:curl|wget)\s+.*https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "Outbound network request to raw public IP"),
    (r"curl\s+-[dF]\s+[@\$]", "Outbound file exfiltration via curl POST/form"),
    (r"(?:chmod\s+777|chown\s+root|useradd|usermod\s+-aG\s+sudo)", "Privilege escalation / insecure file permission alteration"),
    (r"mimikatz|Invoke-Mimikatz|sekurlsa", "Credential dumping tool execution"),
]


def validate_plan_faithfulness_and_linkage(
    raw_sop_text: str,
    execution_plan: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """2-Layer Validation for JIT Converted SOPs.

    Layer 1: Fast Deterministic Python Syntax, Variable Linkage, Tool Catalog & Security Scan (< 1ms).
    Layer 2: LLM Human SOP Faithfulness, Hallucination & Prompt Injection Inspection.

    Returns: (is_valid_bool, validation_errors_list)
    """
    errors = []
    steps = execution_plan.get("steps", [])

    # =========================================================================
    # LAYER 1: FAST DETERMINISTIC PYTHON SYNTAX, LINKAGE & SECURITY CHECK (< 1ms)
    # =========================================================================
    if not steps:
        return False, ["Layer 1 Error: Converted SOP contains zero execution steps."]

    extracted_variables = set()

    for idx, step in enumerate(steps, start=1):
        step_num = step.get("step_number")
        cmd = step.get("command")
        step_type = step.get("step_type", "command")
        desc = (step.get("sop_step_description") or "").lower()
        reasoning = (step.get("step_reasoning") or "").lower()
        parse_instruction = step.get("output_parse_instruction") or step.get("parse_instruction") or ""
        execute_if = step.get("execute_if")

        # Deterministic High-Risk Malicious / Injected Command Filter
        if cmd:
            for pattern, threat_desc in MALICIOUS_COMMAND_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    errors.append(
                        f"Layer 1 Security Violation: Step {idx} command '{cmd}' matched high-risk attack pattern ({threat_desc})."
                    )

        # Reject fabricated placeholder/dummy steps created to bypass validation
        placeholder_markers = [
            "placeholder step",
            "satisfy schema validation",
            "satisfy validation",
            "dummy step",
            "no procedural steps to match against",
        ]
        if any(marker in desc or marker in reasoning for marker in placeholder_markers):
            errors.append(
                f"Layer 1 Error: Step {idx} is a fabricated placeholder step created to bypass validation."
            )

        # Auto-normalize step_type if function_name is provided
        if step_type != "tool_call" and step.get("function_name"):
            target_plat = step.get("platform") or ""
            matching_schema = find_platform_schema(target_plat) if target_plat else None
            if matching_schema and any(fn.get("function_name") == step.get("function_name") for fn in matching_schema.get("functions", [])):
                step["step_type"] = "tool_call"
                step_type = "tool_call"

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
    # LAYER 2: LLM SEMANTIC HUMAN SOP FAITHFULNESS & INJECTION INSPECTION
    # =========================================================================
    print("[PlanValidator Layer 2] Layer 1 passed. Running LLM Faithfulness & Prompt Injection Inspection...")
    try:
        llm = get_llm("planning_validation", temperature=0)
        prompt = (
            JIT_VALIDATOR_COT_SYSTEM_PROMPT
            .replace("{raw_sop_text}", raw_sop_text)
            .replace("{converted_okf_steps}", json.dumps(steps, indent=2))
        )
        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import check_daily_limit, record_call
            check_daily_limit("gemini")
        except Exception as q_err:
            if "Quota" in type(q_err).__name__ or "DailyQuotaExceededError" in str(type(q_err)):
                raise q_err

        res = llm.invoke([{"role": "system", "content": prompt}])

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
                caller="planning_validation",
                model="gemini-2.5-flash" if "gemini" in str(type(llm)).lower() else "mistral-large-latest",
                provider="gemini" if "gemini" in str(type(llm)).lower() else "mistral",
                input_tokens=in_tok,
                output_tokens=out_tok,
                sop_id=execution_plan.get("sop_id") if isinstance(execution_plan, dict) else None
            )
        except Exception as mon_err:
            pass

        content = res.content if hasattr(res, "content") else str(res)
        if isinstance(content, list):
            content = "".join([b.get("text", "") if isinstance(b, dict) else str(b) for b in content])

        # Robust JSON codeblock extraction
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        json_str = match.group(1) if match else (
            re.search(r"(\{.*\})", content, re.DOTALL).group(1) if re.search(r"(\{.*\})", content, re.DOTALL) else content.strip()
        )

        try:
            parsed_json = json.loads(json_str)
            inspection_result = JITFaithfulnessInspectionResult.model_validate(parsed_json)

            verdict_str = "PASSED" if inspection_result.is_faithful else "FAILED"
            print(
                f"[PlanValidator Layer 2] Faithfulness Verdict: {verdict_str} | "
                f"Confidence Score: {inspection_result.confidence_score:.2f} ({inspection_result.confidence_level}) | "
                f"Injection Detected: {inspection_result.injection_detected} | "
                f"Reason: {inspection_result.confidence_reason}"
            )

            # Store validation details in execution plan metadata if dict
            if isinstance(execution_plan, dict):
                execution_plan["validation_confidence_score"] = inspection_result.confidence_score
                execution_plan["validation_confidence_level"] = inspection_result.confidence_level
                execution_plan["validation_confidence_reason"] = inspection_result.confidence_reason
                execution_plan["injection_detected"] = inspection_result.injection_detected
                execution_plan["injection_reasoning"] = inspection_result.injection_reasoning

            # Prompt Injection Detection Failure Gate
            if inspection_result.injection_detected:
                sec_err = (
                    f"Layer 2 Security Error: Prompt injection or malicious command payload detected! "
                    f"Reason: {inspection_result.injection_reasoning} "
                    f"(Flagged steps: {inspection_result.malicious_steps})"
                )
                errors.append(sec_err)
                return False, errors

            if not inspection_result.is_faithful:
                reasons = []
                if inspection_result.dropped_commands:
                    reasons.append(f"Dropped commands/actions: {inspection_result.dropped_commands}")
                if inspection_result.hallucinated_commands:
                    reasons.append(f"Fabricated/hallucinated commands: {inspection_result.hallucinated_commands}")
                if inspection_result.validation_feedback and inspection_result.validation_feedback != "PASSED FAITHFULNESS INSPECTION":
                    reasons.append(f"Feedback: {inspection_result.validation_feedback}")
                
                feedback_str = "; ".join(reasons) if reasons else "Playbook steps failed faithfulness inspection."
                errors.append(f"Layer 2 Faithfulness Error: {feedback_str}")
                return False, errors
        except Exception as parse_err:
            # Fallback if structured json parse failed: check explicit verdict lines
            if re.search(r'"is_faithful"\s*:\s*false', content, re.IGNORECASE) or "STATUS: INVALID" in content:
                errors.append(f"Layer 2 Faithfulness Error: {content[:300]}")
                return False, errors

    except Exception as e:
        print(f"[PlanValidator Layer 2 Warning] LLM Faithfulness check encountered an exception ({e}). Layer 1 passed.")

    return True, []
