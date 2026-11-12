"""
Agent A5: Review Task Manager
=============================
SOP Governance Hub (Option A Single-Gate RBAC):
- Emits RT-xxxxxx identifiers bound to job_id, version, and content hash
- Role Routing: All SOP tiers (L0-L3) route unconditionally to "Security reviewer"
- SLA Deadlines:
    - Confidentiality score >= 60 OR level in (L2, L3) -> 24h deadline
    - Otherwise (L0-L1) -> 48h deadline
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
    """Creates a tracked review task with urgency-based SLA deadline routing."""
    is_urgent = (confidentiality_score >= 60 or confidentiality_level in ("L2", "L3"))
    assigned_role = "Security reviewer"
    hours = 24 if is_urgent else 48
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
