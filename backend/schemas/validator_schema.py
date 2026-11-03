"""
Pydantic Schema for Plan Validator Layer 2 Faithfulness Inspection
==================================================================
Strict typing for the LLM faithfulness and hallucination inspection result.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any


class JITFaithfulnessInspectionResult(BaseModel):
    command_preservation_reasoning: Optional[str] = Field(
        default="All CLI commands and API tool calls from raw text were verified in OKF steps.",
        description="Reasoning verifying if all shell CLI commands and API tool calls from raw human text were preserved in OKF steps."
    )
    hallucination_check_reasoning: Optional[str] = Field(
        default="Zero extra CLI commands or API tool calls were fabricated.",
        description="Reasoning checking if any extra shell CLI commands or API tool calls were fabricated."
    )
    fallback_referral_reasoning: Optional[str] = Field(
        default="Fallback commands and cross-SOP referrals were accurately extracted.",
        description="Reasoning verifying if fallback commands and cross-SOP referrals were accurately extracted."
    )
    injection_reasoning: Optional[str] = Field(
        default="Zero prompt injection or malicious command payloads detected.",
        description="Reasoning evaluating if any steps were injected via prompt overrides or contain malicious backdoor commands."
    )
    is_faithful: bool = Field(
        default=True,
        description="True if the converted OKF playbook is 100% faithful to the raw human SOP and free of injected payloads."
    )
    injection_detected: bool = Field(
        default=False,
        description="True if prompt injection, system prompt override, or malicious backdoor commands were detected."
    )
    malicious_steps: List[int] = Field(
        default_factory=list,
        description="List of step numbers containing injected or malicious commands."
    )
    dropped_commands: List[str] = Field(
        default_factory=list,
        description="List of CLI commands or API tools present in raw text but missing from OKF steps."
    )
    hallucinated_commands: List[str] = Field(
        default_factory=list,
        description="List of CLI commands or API tools fabricated in OKF steps that were NOT in raw text."
    )
    validation_feedback: Optional[str] = Field(
        default="PASSED FAITHFULNESS INSPECTION",
        description="Summary verdict: 'PASSED FAITHFULNESS INSPECTION' or detailed error list."
    )
    confidence_score: float = Field(
        default=1.0,
        description="Confidence score between 0.0 and 1.0 for the faithfulness inspection verdict."
    )
    confidence_level: str = Field(
        default="High",
        description="Confidence level categorization: 'High', 'Medium', or 'Low'."
    )
    confidence_reason: Optional[str] = Field(
        default="All steps, tool calls, and parameters verified against raw SOP without ambiguity.",
        description="Brief rationale for the validation confidence score."
    )

    @field_validator("dropped_commands", "hallucinated_commands", mode="before")
    @classmethod
    def _normalize_command_list(cls, val: Any) -> List[str]:
        if not isinstance(val, list):
            return []
        normalized: List[str] = []
        for item in val:
            if isinstance(item, dict):
                text = item.get("source_action") or item.get("step_description") or item.get("command") or item.get("reason") or str(item)
                normalized.append(str(text))
            elif item is not None:
                normalized.append(str(item))
        return normalized

    @field_validator("malicious_steps", mode="before")
    @classmethod
    def _normalize_malicious_steps(cls, val: Any) -> List[int]:
        if not isinstance(val, list):
            return []
        res = []
        for x in val:
            try:
                res.append(int(x))
            except (ValueError, TypeError):
                pass
        return res
