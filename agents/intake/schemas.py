from typing import Literal, Optional
from pydantic import BaseModel, Field


class TriageResult(BaseModel):
    intent: str = Field(
        description="The primary issue intent classified from ticket text (e.g. 'L1 Network Connectivity Troubleshooting' or 'Disk Error Repair')"
    )
    category: Literal[
        "storage",
        "network",
        "system",
        "hardware",
        "software",
        "logins",
        "mfa",
        "account_management",
        "billing",
        "other",
    ] = Field(description="The primary issue category")
    priority: Literal["critical", "high", "medium", "low"] = Field(
        description="Issue priority level based on business impact"
    )
    
    ticket_details_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0) evaluating the technical specificity, clarity, and completeness of user ticket text and extracted entities (e.g. email, hostname)."
    )
    sop_match_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0) evaluating how closely the reported symptoms match an active OKF playbook or raw PDF upload."
    )
    
    sop_source: Optional[Literal["okf_playbook", "raw_pdf"]] = Field(
        default="okf_playbook",
        description="Indicates whether the matched SOP is an active OKF playbook or a raw PDF file requiring JIT conversion."
    )
    matched_file_path: Optional[str] = Field(
        default=None,
        description="Relative or absolute path to the matched OKF playbook or raw PDF upload file."
    )
    
    detailed_description: str = Field(
        description="Precise technical summary of the issue extracted from ticket text"
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="3 to 8 technical terms for SOP discovery and matching"
    )
    environment: Literal["windows", "linux", "macos", "unknown"] = Field(
        default="windows",
        description="Target OS environment"
    )
    application_name: Optional[str] = Field(
        default=None,
        description="Name of target software application if mentioned in ticket (e.g. Notepad, Visual Studio Code)"
    )
    executable: Optional[str] = Field(
        default=None,
        description="Target executable filename if mentioned or implied in ticket (e.g. notepad.exe, Code.exe)"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Target user account ID if mentioned or implied in ticket (e.g. usr_99812)"
    )
    target_email: Optional[str] = Field(
        default=None,
        description="Target user email address if mentioned in ticket"
    )
    action_reason: Optional[str] = Field(
        default=None,
        description="Stated reason for request (e.g. account locked, password forgotten, suspicious login)"
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="If confidence is low or details missing, question asking user for clarification"
    )