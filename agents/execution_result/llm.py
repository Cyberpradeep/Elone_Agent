"""Structured LLM invocation for CLI output verification in Execution Result Agent."""

import json
from typing import Dict, Any
from shared.llm_config import get_llm
from .schemas import StepAnalysisResult
from .prompts import EXECUTION_RESULT_SYSTEM_PROMPT


def run_result_analysis(
    hostname: str,
    step_num: int,
    target_step: Dict[str, Any],
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    variables: Dict[str, Any]
) -> StepAnalysisResult:
    """Invokes structured LLM to parse CLI stdout/stderr and return StepAnalysisResult."""
    prompt = EXECUTION_RESULT_SYSTEM_PROMPT.format(
        hostname=hostname,
        step_number=step_num + 1,
        step_description=target_step.get("sop_step_description", "Unknown step"),
        command=command,
        exit_code=exit_code,
        expected_output_contains=target_step.get("expected_output_contains", "None"),
        output_variable=target_step.get("output_variable") or "None",
        output_parse_instruction=target_step.get("output_parse_instruction", "None"),
        variables=json.dumps(variables),
        stdout=stdout or "(empty stdout)",
        stderr=stderr or "(empty stderr)",
    )

    try:
        llm = get_llm("execution_result", temperature=0).with_structured_output(StepAnalysisResult)
        return llm.invoke([{"role": "user", "content": prompt}])
    except Exception as e:
        print(f"[Execution Result LLM Error] Parsing failed: {e}. Falling back based on exit code.")
        return StepAnalysisResult(
            extracted_variables=[],
            next_action="SUCCESS" if exit_code == 0 else "RETRY",
            reasoning=f"LLM parsing fallback ({e}) based on exit code {exit_code}."
        )
