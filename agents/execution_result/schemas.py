"""Pydantic schemas for Execution Result Agent."""

from typing import Literal, List
from pydantic import BaseModel, Field


class VariableEntry(BaseModel):
    """Single extracted variable key-value pair."""
    key: str = Field(description="Variable key name in snake_case.")
    value: str = Field(description="Variable string value.")


class StepAnalysisResult(BaseModel):
    """Structured LLM verification output for a single execution step."""
    extracted_variables: List[VariableEntry] = Field(
        default_factory=list,
        description=(
            "List of key-value variables extracted from stdout/stderr according to output_parse_instruction. "
            "Keys MUST be clean snake_case strings (e.g. key='dhcp_failure', value='true')."
        )
    )
    next_action: Literal["SUCCESS", "RETRY", "ESCALATE"] = Field(
        description=(
            "SUCCESS: Command completed (exit_code == 0) and output was parsed cleanly. "
            "Note: System fault conditions (e.g. dhcp_failure=true) are stored in extracted_variables, "
            "NOT set to RETRY, because downstream steps handle branching. "
            "RETRY: Command failed to execute (exit_code != 0, timeout, command not found). "
            "ESCALATE: Critical permission denied or unrecoverable error."
        )
    )
    reasoning: str = Field(
        description="Brief explanation of findings and extracted variables."
    )

