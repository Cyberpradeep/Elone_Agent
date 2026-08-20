"""
Pydantic Schema for Plan Validator Layer 2 Faithfulness Inspection
==================================================================
Strict typing for the LLM faithfulness and hallucination inspection result.
"""

from pydantic import BaseModel, Field
from typing import List


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
    dropped_commands: List[str] = Field(
        default_factory=list,
        description="List of CLI commands or API tools present in raw text but missing from OKF steps."
    )
    hallucinated_commands: List[str] = Field(
        default_factory=list,
        description="List of CLI commands or API tools fabricated in OKF steps that were NOT in raw text."
    )
    validation_feedback: str = Field(
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
    confidence_reason: str = Field(
        default="All steps, tool calls, and parameters verified against raw SOP without ambiguity.",
        description="Brief rationale for the validation confidence score."
    )
