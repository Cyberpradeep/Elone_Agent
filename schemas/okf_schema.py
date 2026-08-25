"""
Pydantic Schemas for OKF Playbook Structure & Validation
=========================================================
Strict structural typing for converted OKF Playbooks.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class OKFStepModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_number: int = Field(..., description="1-indexed step number")
    sop_step_description: str = Field(..., description="Description of the SOP step action")
    step_type: str = Field(..., description="Step type: 'tool_call' or 'command'")
    step_reasoning: Optional[str] = Field(
        None,
        description="LLM's reasoning for why THIS specific step_type/tool/command was chosen for this step "
                    "(e.g. which of the 4 Verification Gates passed/failed and why, why this exact command/function "
                    "over any alternative, why these particular comm_inputs/placeholders were used).",
    )
    platform: Optional[str] = Field(None, description="Platform identifier (e.g. system, solandra, auth0, airretailer)")
    function_name: Optional[str] = Field(None, description="Tool function name for tool_call steps")
    comm_inputs: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Input parameters for tool_call")
    command: Optional[str] = Field(None, description="CLI command string for command steps")
    fallback_command: Optional[str] = Field(None, description="Fallback CLI command string if primary fails")
    fallback_sop_id: Optional[str] = Field(None, description="SOP ID to invoke if step fails")
    parse_instruction: Optional[str] = Field(
        None,
        description="Instructions to parse stdout/response into variables (e.g. 'If output contains Debugger, set variables.ifeo_blocked = true, else variables.ifeo_blocked = false')",
    )
    execute_if: Optional[str] = Field(
        None,
        description="Conditional execution expression referencing preceding step variables (e.g. 'variables.ifeo_blocked == true')",
    )
    timeout_seconds: Optional[int] = Field(30, description="Execution timeout in seconds")

    @model_validator(mode="before")
    @classmethod
    def _normalize_dict_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize parse_instruction from aliases
            if "output_parse_instruction" in data and not data.get("parse_instruction"):
                data["parse_instruction"] = data["output_parse_instruction"]
        return data

    @field_validator("step_type")
    @classmethod
    def validate_step_type(cls, v: str) -> str:
        v_clean = str(v).lower().strip()
        if v_clean not in {"tool_call", "command"}:
            raise ValueError(f"Invalid step_type '{v}'. Must be 'tool_call' or 'command'.")
        return v_clean


class OKFPlaybookModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sop_id: str = Field(..., description="Unique SOP ID (e.g. SOP-NET-001)")
    title: str = Field(..., description="Human-readable title of the Playbook")
    platform: Optional[str] = Field(None, description="Primary platform (e.g. solandra, auth0, airretailer)")
    category: str = Field(..., description="SOP category (e.g. network, identity, system)")
    target_os: Optional[str] = Field("windows", description="Target operating system")
    description: Optional[str] = Field(None, description="Playbook overview description")
    confidence_score: Optional[float] = Field(0.95, description="Confidence score between 0.0 and 1.0 representing conversion fidelity")
    confidence_level: Optional[str] = Field("High", description="Confidence level categorization: 'High', 'Medium', or 'Low'")
    confidence_reason: Optional[str] = Field(None, description="Reasoning justifying the assigned confidence score")
    required_entities: List[str] = Field(default_factory=list, description="Required entity dynamic placeholders")
    trigger_words: List[str] = Field(default_factory=list, description="Trigger keywords for playbook lookup")
    reasoning_chain: List[str] = Field(default_factory=list, description="8-stage CoT reasoning log")
    steps: List[OKFStepModel] = Field(..., description="List of execution steps")

    @field_validator("steps")
    @classmethod
    def validate_steps_non_empty(cls, v: List[OKFStepModel]) -> List[OKFStepModel]:
        if not v:
            raise ValueError("Playbook must contain at least 1 execution step.")
        return v
