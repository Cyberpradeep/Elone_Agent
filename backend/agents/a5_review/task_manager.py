"""
Agent A5: Review Task Manager
=============================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.5 & 13)
- Emits RT-xxxxxx identifiers bound to job_id, version, and content hash
- SLA Routing:
    - Confidentiality score >= 60 OR level in (L2, L3) -> "Security reviewer", 24h deadline
    - Otherwise -> "Process owner", 48h deadline
"""

import datetime
from typing import Optional
from schemas.governance_models import (
    ReviewTask,
    generate_review_task_id,
    _utc_now_iso,
)


def create_review_task(
    sop_id: str,
    job_id: str,
    version: int,
    content_sha256: str,
    uploaded_by: str,
    confidentiality_score: int,
    confidentiality_level: str,
) -> ReviewTask:
    """Creates a tracked review task with SLA deadline routing."""
    # SLA routing per Section 13:
    # Score >= 60 or L2/L3 routes to Security Reviewer with 24h deadline; otherwise Process Owner with 48h deadline.
    requires_security = (confidentiality_score >= 60 or confidentiality_level in ("L2", "L3"))
    assigned_role = "Security reviewer" if requires_security else "Process owner"
    hours = 24 if requires_security else 48
    due_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)

    return ReviewTask(
        task_id=generate_review_task_id(),
        sop_id=sop_id,
        job_id=job_id,
        version=version,
        content_sha256=content_sha256,
        assigned_role=assigned_role,
        due_date=due_dt.isoformat(),
        uploaded_by=uploaded_by,
        status="pending",
    )
