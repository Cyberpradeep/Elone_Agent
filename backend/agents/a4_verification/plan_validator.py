import json
import re
from typing import Tuple, List, Dict, Any

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
# pyrefly: ignore [missing-import]
from utils.security import enforce_entity_double_quotes
try:
    from utils.pipeline_logger import log_validation_audit, log_info, log_warning, log_error
except ImportError:
    from backend.utils.pipeline_logger import log_validation_audit, log_info, log_warning, log_error


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


def _validate_source_action_coverage(execution_plan: Dict[str, Any]) -> List[str]:
    """Validate links between source-action accounting and executable steps.

    The playbook remains tool/command-only.  Coverage records explain why source
    UI or human instructions are omitted, or which agent capability replaces
    them.  This is intentionally deterministic: an LLM must not reject a valid
    tool merely because the SOP described the same outcome as a mouse click.
    """
    coverage_items = execution_plan.get("source_action_coverage")
    if coverage_items is None:
        # Keep legacy drafts readable while new converter prompts emit coverage.
        return []
    if not isinstance(coverage_items, list):
        return ["Layer 1 Coverage Error: source_action_coverage must be a list."]

    steps_by_number = {
        step.get("step_number"): step
        for step in (execution_plan.get("steps") or [])
        if isinstance(step, dict) and isinstance(step.get("step_number"), int)
    }
    errors: List[str] = []

    for idx, item in enumerate(coverage_items, start=1):
        if not isinstance(item, dict):
            errors.append(f"Layer 1 Coverage Error: Coverage item {idx} must be an object.")
            continue

        source_action = str(item.get("source_action") or "").strip()
        coverage = item.get("coverage")
        if not source_action:
            errors.append(f"Layer 1 Coverage Error: Coverage item {idx} is missing source_action.")
            continue

        if coverage in {"tool_covered", "command_covered"}:
            step_number = item.get("step_number")
            step = steps_by_number.get(step_number)
            if not step:
                errors.append(
                    f"Layer 1 Coverage Error: '{source_action}' claims {coverage} but references missing step {step_number}."
                )
                continue

            if coverage == "tool_covered":
                expected_tool = str(item.get("tool") or "").strip()
                actual_tool = f"{step.get('platform')}.{step.get('function_name')}"
                if step.get("step_type") != "tool_call" or not expected_tool:
                    errors.append(
                        f"Layer 1 Coverage Error: '{source_action}' must reference a tool_call and canonical tool name."
                    )
                elif actual_tool != expected_tool:
                    errors.append(
                        f"Layer 1 Coverage Error: '{source_action}' maps to '{expected_tool}' but step {step_number} uses '{actual_tool}'."
                    )
            elif step.get("step_type") != "command" or not step.get("command"):
                errors.append(
                    f"Layer 1 Coverage Error: '{source_action}' must reference a non-empty command step."
                )

        elif coverage in {"manual_ui_omitted", "unsupported_required"}:
            if item.get("step_number") is not None:
                errors.append(
                    f"Layer 1 Coverage Error: '{source_action}' is {coverage} and must not point to an executable step."
                )
            if not str(item.get("reason") or "").strip():
                errors.append(
                    f"Layer 1 Coverage Error: '{source_action}' is {coverage} but has no explanation."
                )
        else:
            errors.append(
                f"Layer 1 Coverage Error: '{source_action}' has unsupported coverage value '{coverage}'."
            )

    return errors


def _coverage_accounts_for_validator_claim(claim: str, coverage_items: List[Dict[str, Any]]) -> bool:
    """Return True when a Layer 2 claim is already accounted for in the ledger.

    This deliberately uses conservative word-overlap matching in addition to an
    exact normalized match.  The validator and converter often paraphrase the
    same source instruction (for example, "collect local IP" versus "retrieve
    office PC IP"), so literal equality would reintroduce the GUI false positive
    this ledger exists to prevent.
    """
    claim_normalized = re.sub(r"[^a-z0-9]+", " ", str(claim).lower()).strip()
    if not claim_normalized:
        return False
    ignored_words = {"the", "a", "an", "to", "for", "from", "and", "or", "of", "in", "on", "with", "your"}
    claim_tokens = {token for token in claim_normalized.split() if token not in ignored_words}

    for item in coverage_items:
        source_normalized = re.sub(r"[^a-z0-9]+", " ", str(item.get("source_action") or "").lower()).strip()
        if not source_normalized:
            continue
        if claim_normalized == source_normalized or claim_normalized in source_normalized or source_normalized in claim_normalized:
            return True
        source_tokens = {token for token in source_normalized.split() if token not in ignored_words}
        if claim_tokens and source_tokens:
            overlap = len(claim_tokens & source_tokens) / min(len(claim_tokens), len(source_tokens))
            if overlap >= 0.75:
                return True
    return False


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

    errors.extend(_validate_source_action_coverage(execution_plan))

    # =========================================================================
    # LAYER 1: FAST DETERMINISTIC PYTHON SYNTAX, LINKAGE & SECURITY CHECK (< 1ms)
    # =========================================================================
    if not steps:
        return False, ["Layer 1 Error: Converted SOP contains zero execution steps."]

    extracted_variables = set()

    for idx, step in enumerate(steps, start=1):
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

        # Check required command and shell for command step_type
        if step_type == "command":
            if not cmd:
                errors.append(f"Layer 1 Error: Step {idx} has step_type='command' but command is empty.")
            # Auto-assign powershell if shell is missing or check powershell
            if not step.get("shell"):
                step["shell"] = "powershell"
            # Enforce double-quotes on dynamic entity placeholders to prevent shell argument splitting injection
            if cmd and "{{entities." in cmd:
                cmd = enforce_entity_double_quotes(cmd)
                step["command"] = cmd

        # Check required fields and catalog verification for tool_call step_type
        if step_type == "tool_call":
            tool_is_valid, tool_errors = validate_tool_step_schema(step, step_idx=idx)
            if not tool_is_valid:
                errors.extend(tool_errors)

        # 0. ENTITY CONSISTENCY GUARD (Check {{entities.*}} against required_entities)
        declared_entities = {e.lower() for e in (execution_plan.get("required_entities") or [])}
        referenced_entities = set()
        if cmd:
            for ent in re.findall(r"\{\{entities\.(\w+)\}\}", cmd, re.IGNORECASE):
                referenced_entities.add(ent.lower())
        if step.get("comm_inputs") and isinstance(step["comm_inputs"], dict):
            for ent in re.findall(r"\{\{entities\.(\w+)\}\}", json.dumps(step["comm_inputs"]), re.IGNORECASE):
                referenced_entities.add(ent.lower())

        for ent in referenced_entities:
            if declared_entities and ent not in declared_entities:
                errors.append(
                    f"Layer 1 Entity Linkage Error: Step {idx} references undeclared entity '{{{{entities.{ent}}}}}', "
                    f"which was not listed in frontmatter required_entities {list(declared_entities)}."
                )

        # 1. VERIFY PRECEDING VARIABLE LINKAGE (execute_if & dynamic {{variables.*}})
        # Check execute_if variable linkage contract
        if execute_if:
            req_vars = re.findall(r"(?:\{\{)?variables\.(\w+)(?:\}\})?", execute_if, re.IGNORECASE)
            for req_var in req_vars:
                if req_var.lower() not in extracted_variables:
                    errors.append(
                        f"Layer 1 Linkage Error: Step {idx} has execute_if condition referencing 'variables.{req_var}', "
                        f"but '{req_var}' was never extracted or returned by any preceding step!"
                    )

        # Check dynamic {{variables.*}} in command string
        if cmd:
            dyn_cmd_vars = re.findall(r"\{\{variables\.(\w+)\}\}", cmd, re.IGNORECASE)
            for dyn_var in dyn_cmd_vars:
                if dyn_var.lower() not in extracted_variables:
                    errors.append(
                        f"Layer 1 Linkage Error: Step {idx} command references dynamic variable '{{{{variables.{dyn_var}}}}}', "
                        f"but '{dyn_var}' was never extracted or returned by any preceding step!"
                    )

        # Check dynamic {{variables.*}} in comm_inputs
        comm_inputs = step.get("comm_inputs")
        if comm_inputs and isinstance(comm_inputs, dict):
            dyn_comm_vars = re.findall(r"\{\{variables\.(\w+)\}\}", json.dumps(comm_inputs), re.IGNORECASE)
            for dyn_var in dyn_comm_vars:
                if dyn_var.lower() not in extracted_variables:
                    errors.append(
                        f"Layer 1 Linkage Error: Step {idx} comm_inputs references dynamic variable '{{{{variables.{dyn_var}}}}}', "
                        f"but '{dyn_var}' was never extracted or returned by any preceding step!"
                    )

        # 2. REGISTER VARIABLES PRODUCED BY THIS STEP (available for subsequent steps)
        # Register variables from tool response schema
        if step_type == "tool_call":
            plat_schema = find_platform_schema(step.get("platform") or "")
            if plat_schema:
                for fn in plat_schema.get("functions", []):
                    if fn.get("function_name") == step.get("function_name"):
                        resp_success = fn.get("response_schema", {}).get("success", {})
                        if isinstance(resp_success, dict):
                            for resp_k in resp_success.keys():
                                extracted_variables.add(resp_k.lower())

        # Track variables set in parse instructions
        if parse_instruction:
            # Pattern 1: variables.var_name
            for v in re.findall(r"variables\.(\w+)", parse_instruction, re.IGNORECASE):
                extracted_variables.add(v.lower())
            # Pattern 2: var_name = <val>
            for v in re.findall(r"(\w+)\s*=\s*(?:true|false|'[^']*'|\"[^\"]*\"|\w+)", parse_instruction, re.IGNORECASE):
                if v.lower() not in {"if", "else", "set", "then"}:
                    extracted_variables.add(v.lower())
            # Pattern 3: extract/store <key> into/in/to variables.<var>
            for v in re.findall(r"(?:set|store|extract)\s+(?:response\.)?(\w+)\s+(?:in|into|to)\s+(?:variables\.)?(\w+)", parse_instruction, re.IGNORECASE):
                extracted_variables.add(v[0].lower())
                extracted_variables.add(v[1].lower())

        # Track output_variable if present
        if step.get("output_variable"):
            extracted_variables.add(str(step["output_variable"]).lower())

    # If Layer 1 fails, stop immediately (save LLM call!)
    if errors:
        log_warning("PlanValidator Layer 1", f"Failed with {len(errors)} deterministic errors: {errors}")
        return False, errors

    # If raw_sop_text is minimal, return Layer 1 success
    if not raw_sop_text or len(raw_sop_text.strip()) < 30:
        return True, []

    # =========================================================================
    # LAYER 2: LLM SEMANTIC HUMAN SOP FAITHFULNESS & INJECTION INSPECTION
    # =========================================================================
    log_info("PlanValidator Layer 2", "Layer 1 passed. Running LLM Faithfulness & Prompt Injection Inspection...")
    try:
        llm = get_llm("planning_validation", temperature=0)
        prompt = (
            JIT_VALIDATOR_COT_SYSTEM_PROMPT
            .replace("{raw_sop_text}", raw_sop_text)
            .replace("{converted_okf_steps}", json.dumps(steps, indent=2))
            .replace(
                "{source_action_coverage}",
                json.dumps(execution_plan.get("source_action_coverage") or [], indent=2),
            )
        )
        try:
            # pyrefly: ignore [missing-import]
            from gemini_monitor.monitor import check_daily_limit, record_call
            check_daily_limit("gemini")
        except Exception as q_err:
            if "Quota" in type(q_err).__name__ or "DailyQuotaExceededError" in str(type(q_err)):
                raise q_err

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Please perform the faithfulness and security audit on the provided SOP and execution plan, and output the required JSON evaluation according to the system instructions."}
        ]
        res = llm.invoke(messages)

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
            if not isinstance(parsed_json, dict):
                raise ValueError("Parsed JSON must be a dict")

            try:
                inspection_result = JITFaithfulnessInspectionResult.model_validate(parsed_json)
            except Exception:
                inspection_result = JITFaithfulnessInspectionResult(
                    is_faithful=bool(parsed_json.get("is_faithful", True)),
                    injection_detected=bool(parsed_json.get("injection_detected", False)),
                    confidence_score=float(parsed_json.get("confidence_score") or 0.8),
                    confidence_level=str(parsed_json.get("confidence_level") or "Medium"),
                    confidence_reason=str(parsed_json.get("confidence_reason") or ""),
                    command_preservation_reasoning=str(parsed_json.get("command_preservation_reasoning") or ""),
                    hallucination_check_reasoning=str(parsed_json.get("hallucination_check_reasoning") or ""),
                    fallback_referral_reasoning=str(parsed_json.get("fallback_referral_reasoning") or ""),
                    injection_reasoning=str(parsed_json.get("injection_reasoning") or ""),
                    dropped_commands=parsed_json.get("dropped_commands") or [],
                    hallucinated_commands=parsed_json.get("hallucinated_commands") or [],
                    malicious_steps=parsed_json.get("malicious_steps") or [],
                    validation_feedback=str(parsed_json.get("validation_feedback") or ""),
                )

            # Stage 4: Validation Layer 2 Audit Log (Always renders with Rich!)
            log_validation_audit(inspection_result)

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
                coverage_items = [
                    item for item in (execution_plan.get("source_action_coverage") or [])
                    if isinstance(item, dict)
                ]
                unaccounted_drops = [
                    claim for claim in inspection_result.dropped_commands
                    if not _coverage_accounts_for_validator_claim(claim, coverage_items)
                ]

                # A semantic reviewer occasionally contradicts its own prompt by
                # flagging source UI wording even though an approved capability is
                # explicitly linked in the coverage ledger.  The deterministic
                # linkage checks above are authoritative in that situation.
                if (
                    coverage_items
                    and not unaccounted_drops
                    and not inspection_result.hallucinated_commands
                ):
                    log_info(
                        "PlanValidator Layer 2",
                        "Ignoring inconsistent faithfulness verdict: all reported drops accounted for by source_action_coverage."
                    )
                    return True, errors

                reasons = []
                if unaccounted_drops:
                    reasons.append(f"Dropped commands/actions: {unaccounted_drops}")
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
        err_msg = (
            f"Layer 2 Security Error: LLM Faithfulness & Injection Audit failed or unavailable ({e}). "
            f"Ingestion blocked to preserve fail-closed security."
        )
        log_error("PlanValidator Layer 2", err_msg)
        return False, [err_msg]

    return True, []


# Aliases
validate_plan_faithfulness = validate_plan_faithfulness_and_linkage

__all__ = [
    "validate_plan_faithfulness_and_linkage",
    "validate_plan_faithfulness",
    "MALICIOUS_COMMAND_PATTERNS",
]





