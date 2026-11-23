"""Intake Issue and Incident Ticket Contract Models.

Strictly encapsulates incoming ticket information with tenant boundaries,
role clearance requirements, and entity dictionaries.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class IssuePriorityEnum(str, Enum):
    P1_CRITICAL = "P1_CRITICAL"
    P2_HIGH = "P2_HIGH"
    P3_MEDIUM = "P3_MEDIUM"
    P4_LOW = "P4_LOW"


class IssueSourceEnum(str, Enum):
    MANUAL = "MANUAL"
    SERVICENOW_WEBHOOK = "SERVICENOW_WEBHOOK"
    EMAIL = "EMAIL"
    SYNTHETIC_TEST = "SYNTHETIC_TEST"


EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


class Issue(BaseModel):
    """Immutable representation of an incoming support issue or incident."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_id: str = Field(
        ...,
        pattern=r"^INC-\d{4,8}$",
        description="Standard incident identifier, e.g. INC-2041",
    )
    tenant_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Tenant boundary isolation key",
    )
    source: IssueSourceEnum = IssueSourceEnum.MANUAL
    raw_text: str = Field(
        ...,
        min_length=5,
        max_length=10000,
        description="Untrusted raw ticket text from user or webhook",
    )
    sanitized_text: Optional[str] = Field(
        default=None,
        description="Text stripped of prompt injection patterns and delimiters",
    )
    customer_email: str = Field(
        ...,
        pattern=EMAIL_REGEX,
        description="Customer or requester email address",
    )
    requester_role: str = Field(
        default="operator",
        description="Role claim extracted from authenticated token",
    )
    requester_clearance: str = Field(
        default="INTERNAL",
        description="Clearance level: INTERNAL, CONFIDENTIAL, or RESTRICTED",
    )
    priority: IssuePriorityEnum = IssuePriorityEnum.P3_MEDIUM
    entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted entities such as hostname, service, user, port",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

