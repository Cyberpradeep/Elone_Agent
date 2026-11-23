"""Intake & Understanding Agent (Module A5).

Ingests raw incident tickets, performs security fencing, integrates domain
asset lookups from shared/asset_lookup.py, validates contracts.issue.Issue,
and enforces catalog retrieval thresholds.
"""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from contracts.issue import Issue, IssuePriorityEnum, IssueSourceEnum
from contracts.sop import SOPReference
from contracts.state import EngineStateEnum
from shared.asset_lookup import extract_and_lookup_asset, lookup_asset_by_identifier
from agents.a1_understanding.sanitizer import (
    detect_prompt_injection,
    sanitize_and_fence_text,
    scrub_sensitive_secrets,
)
from agents.a1_understanding.retrieval import match_sop_catalog, RetrievalResult


class IntakeResult(BaseModel):
    """Result of intake triage, asset resolution, and catalog gating."""
    issue: Issue
    matched_sop: Optional[SOPReference]
    match_confidence: float
    workflow_state: EngineStateEnum
    prompt_injection_detected: bool
    status_reason: str


def _extract_email(text: str) -> Optional[str]:
    """Extract first valid email address from raw text."""
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    return match.group(0) if match else None


def intake_ticket(
    raw_text: str,
    tenant_id: str,
    issue_id: str,
    customer_email: Optional[str] = None,
    source: IssueSourceEnum = IssueSourceEnum.MANUAL,
    priority: IssuePriorityEnum = IssuePriorityEnum.P3_MEDIUM,
    catalog: Optional[List[SOPReference]] = None,
) -> IntakeResult:
    """Ingest, sanitize, enrich with asset inventory, and match to SOP catalog."""
    # 1. Prompt Injection Scanning
    injection_detected, matched_patterns = detect_prompt_injection(raw_text)

    # 2. Sanitization, Secret Scrubbing, and Delimiter Fencing
    sanitized_body = sanitize_and_fence_text(raw_text)

    # 3. Domain Asset & Inventory Lookup (Reusing shared/asset_lookup.py)
    enriched_entities = extract_and_lookup_asset(raw_text)
    # Scrub passwords from asset inventory so credentials never leak into Issue entities
    if "password" in enriched_entities:
        enriched_entities.pop("password")

    # 4. Resolve Customer Email
    resolved_email = customer_email or enriched_entities.get("email") or _extract_email(raw_text)
    if not resolved_email:
        resolved_email = "requester@internal.corp"

    # 5. Build Immutable Issue Contract Model
    issue = Issue(
        issue_id=issue_id,
        tenant_id=tenant_id,
        source=source,
        raw_text=raw_text,
        sanitized_text=sanitized_body,
        customer_email=resolved_email,
        priority=priority,
        entities=enriched_entities,
    )

    # 6. SOP Catalog Matching & Confidence Gate (if catalog provided)
    matched_sop: Optional[SOPReference] = None
    confidence = 0.0
    workflow_state = EngineStateEnum.TRIAGED
    reason = "Ticket successfully ingested and triaged."

    if injection_detected:
        reason = f"Security Warning: Prompt injection pattern detected: {matched_patterns}. Body was fenced."

    if catalog:
        retrieval: RetrievalResult = match_sop_catalog(raw_text, catalog, tenant_id=tenant_id)
        matched_sop = retrieval.matched_sop
        confidence = retrieval.confidence
        reason = retrieval.status_reason

        if retrieval.requires_human:
            workflow_state = EngineStateEnum.NEEDS_HUMAN
        else:
            workflow_state = EngineStateEnum.TRIAGED

    return IntakeResult(
        issue=issue,
        matched_sop=matched_sop,
        match_confidence=confidence,
        workflow_state=workflow_state,
        prompt_injection_detected=injection_detected,
        status_reason=reason,
    )
