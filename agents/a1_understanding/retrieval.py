"""Tenant-Isolated SOP Retrieval and Ambiguity Detection Gate.

Implements:
- Minimum confidence gate: score < 0.82 -> NEEDS_HUMAN (Edge Case 1).
- Ambiguity detection gate: top 2 score delta <= 0.05 -> NEEDS_HUMAN (Edge Case 2).
- Tenant isolation: Tenant A cannot match or view Tenant B SOPs (Edge Case 22).
"""

import re
from typing import Dict, List, Optional, Set
from pydantic import BaseModel
from contracts.sop import SOPReference


MIN_CONFIDENCE_THRESHOLD = 0.82
AMBIGUITY_DELTA_THRESHOLD = 0.05

STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "in", "at", "to", "for", "on", "and", "or", "of", "with", "by", "as",
    "from", "into", "it", "this", "that", "these", "those", "are", "was", "were", "be", "been",
}

GENERIC_TERMS: Set[str] = {
    "procedure", "recovery", "service", "services", "system", "systems", "guide", "process",
    "management", "fix", "issue", "problem", "ticket", "task", "job", "action", "run", "remediation",
}


class MatchCandidate(BaseModel):
    """Ranked SOP match candidate with computed similarity score."""
    sop: SOPReference
    score: float


class RetrievalResult(BaseModel):
    """Outcome of SOP catalog retrieval and governance gating."""
    matched_sop: Optional[SOPReference]
    confidence: float
    candidates: List[MatchCandidate]
    requires_human: bool
    status_reason: str


def _tokenize(text: str) -> Set[str]:
    """Extract lowercased alphanumeric tokens."""
    return set(re.findall(r"[a-z0-9_-]{2,}", text.lower()))


def compute_match_score(query_text: str, sop: SOPReference) -> float:
    """Compute deterministic relevance score in range [0.0, 1.0]."""
    if not query_text:
        return 0.0

    # 1. Exact SOP ID reference yields immediate 1.0 match
    if sop.sop_id.lower() in query_text.lower():
        return 1.0

    query_tokens = _tokenize(query_text) - STOPWORDS
    if not query_tokens:
        return 0.0

    target_tokens = _tokenize(sop.title) - STOPWORDS
    core_target = target_tokens - GENERIC_TERMS
    if not core_target:
        core_target = target_tokens

    overlap = query_tokens.intersection(target_tokens)
    if not overlap:
        return 0.0

    core_overlap = query_tokens.intersection(core_target)
    core_recall = len(core_overlap) / len(core_target) if core_target else 0.0
    overall_recall = len(overlap) / len(target_tokens) if target_tokens else 0.0

    # Scoring algorithm:
    # If all core domain keywords are satisfied, baseline is 0.85 + bonus for general tokens
    if core_recall >= 1.0 and len(core_target) >= 2:
        score = 0.85 + (0.15 * overall_recall)
    elif core_recall >= 0.75:
        score = 0.70 + (0.25 * core_recall)
    else:
        score = (0.50 * core_recall) + (0.30 * overall_recall)

    return round(min(1.0, score), 3)


def match_sop_catalog(
    query_text: str,
    catalog: List[SOPReference],
    tenant_id: str,
) -> RetrievalResult:
    """Search tenant-filtered SOP catalog and enforce confidence & ambiguity gates."""
    # 1. Enforce Multi-Tenant Isolation (Edge Case 22)
    tenant_catalog = [sop for sop in catalog if sop.tenant_id == tenant_id]

    if not tenant_catalog:
        return RetrievalResult(
            matched_sop=None,
            confidence=0.0,
            candidates=[],
            requires_human=True,
            status_reason=f"No SOPs found in catalog for tenant '{tenant_id}' (Edge Case 22: Tenant Isolation)",
        )

    # 2. Score candidates
    scored_candidates: List[MatchCandidate] = []
    for sop in tenant_catalog:
        score = compute_match_score(query_text, sop)
        scored_candidates.append(MatchCandidate(sop=sop, score=score))

    # Sort descending by score
    scored_candidates.sort(key=lambda c: c.score, reverse=True)
    top_candidate = scored_candidates[0] if scored_candidates else None

    # 3. Minimum Confidence Check (Edge Case 1)
    if not top_candidate or top_candidate.score < MIN_CONFIDENCE_THRESHOLD:
        score_val = top_candidate.score if top_candidate else 0.0
        return RetrievalResult(
            matched_sop=None,
            confidence=score_val,
            candidates=scored_candidates,
            requires_human=True,
            status_reason=(
                f"SOP match confidence {score_val:.2f} is below minimum threshold "
                f"{MIN_CONFIDENCE_THRESHOLD:.2f}. Human triage required (Edge Case 1)."
            ),
        )

    # 4. Ambiguity Detection Gate (Edge Case 2)
    if len(scored_candidates) > 1:
        second_candidate = scored_candidates[1]
        delta = top_candidate.score - second_candidate.score
        if delta <= AMBIGUITY_DELTA_THRESHOLD and second_candidate.score >= (MIN_CONFIDENCE_THRESHOLD - 0.10):
            return RetrievalResult(
                matched_sop=None,
                confidence=top_candidate.score,
                candidates=scored_candidates,
                requires_human=True,
                status_reason=(
                    f"Ambiguous SOP match detected between '{top_candidate.sop.sop_id}' ({top_candidate.score:.2f}) "
                    f"and '{second_candidate.sop.sop_id}' ({second_candidate.score:.2f}) "
                    f"(delta={delta:.3f} <= {AMBIGUITY_DELTA_THRESHOLD}). Escalating to human (Edge Case 2)."
                ),
            )

    # Success: Single, confident, unambiguous match
    return RetrievalResult(
        matched_sop=top_candidate.sop,
        confidence=top_candidate.score,
        candidates=scored_candidates,
        requires_human=False,
        status_reason="Unambiguous SOP match found above confidence threshold.",
    )
