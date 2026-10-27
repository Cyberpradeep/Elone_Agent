"""
Agent A3: Confidentiality Scoring Engine
========================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.3 & 11)
Deterministic 0-100 confidentiality score, L0-L3 tier assignment,
rules vs AI evidence, non-negotiable AI floor rule, and conflict detection.
"""

import re
from typing import List, Dict, Any, Tuple, Optional

TIER_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
TIER_LABELS = {
    "L0": "L0 Public",
    "L1": "L1 Internal",
    "L2": "L2 Confidential",
    "L3": "L3 Restricted",
}

INFRASTRUCTURE_PATTERNS = [
    re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
    re.compile(r"\b[a-zA-Z0-9_\.-]+\.(?:corp|internal|local|lan|priv|intranet|example)\b", re.IGNORECASE),
    re.compile(r"\b(?:HKLM\\|HKCU\\|LDAP://|DC=|OU=|CN=)\b", re.IGNORECASE),
    re.compile(r"\b(?:vpn\.[a-z0-9_\.-]+|portal\.[a-z0-9_\.-]+|gateway\.[a-z0-9_\.-]+)\b", re.IGNORECASE),
]

CONFIDENTIAL_LABEL_PATTERN = re.compile(
    r"\b(strictly\s+confidential|confidential|internal\s+only|company\s+proprietary|"
    r"proprietary\s+and\s+confidential|do\s+not\s+distribute|restricted\s+access)\b",
    re.IGNORECASE,
)


def score_to_tier(score: int) -> str:
    """Deterministic tier mapping per Section 11:
    L0 Public: < 21 | L1 Internal: 21-50 | L2 Confidential: 51-75 | L3 Restricted: >= 76
    """
    if score < 21:
        return "L0"
    if score <= 50:
        return "L1"
    if score <= 75:
        return "L2"
    return "L3"


def compute_confidentiality_score(
    text: str,
    dlp_stats: Optional[Dict[str, int]] = None,
    is_ocr: bool = False,
    ai_advisory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Computes deterministic 0-100 confidentiality score and assigns L0-L3 tier."""
    dlp_stats = dlp_stats or {}
    ai_advisory = ai_advisory or {}

    score = 5
    evidence_categories = ["baseline_internal_sop"]
    breakdown = [{"label": "Baseline for any internal SOP", "points": 5, "source": "rule"}]

    secrets_count = (
        dlp_stats.get("passwords", 0)
        + dlp_stats.get("api_keys", 0)
        + dlp_stats.get("private_keys", 0)
    )
    quarantine_triggered = secrets_count > 0
    if quarantine_triggered:
        score += 45
        evidence_categories.append("credentials_or_secrets")
        breakdown.append({
            "label": f"Credentials or secrets detected ({secrets_count} items - triggers quarantine)",
            "points": 45,
            "source": "rule",
        })

    infra_matches = set()
    if text:
        for pat in INFRASTRUCTURE_PATTERNS:
            for match in pat.findall(text):
                infra_matches.add(match.lower())
    infra_count = len(infra_matches)
    if infra_count > 0:
        infra_pts = min(25, 10 + (infra_count - 1) * 5)
        score += infra_pts
        evidence_categories.append("internal_infrastructure")
        breakdown.append({
            "label": f"Internal infrastructure ({infra_count} unique items)",
            "points": infra_pts,
            "source": "rule",
        })

    pii_count = dlp_stats.get("emails", 0) + dlp_stats.get("phones", 0)
    if pii_count > 0:
        pii_pts = min(25, 10 + (pii_count - 1) * 5)
        score += pii_pts
        evidence_categories.append("personal_data")
        breakdown.append({
            "label": f"Personal data / PII ({pii_count} items)",
            "points": pii_pts,
            "source": "rule",
        })

    if text and CONFIDENTIAL_LABEL_PATTERN.search(text):
        score += 15
        evidence_categories.append("explicit_confidentiality_label")
        breakdown.append({
            "label": "Explicit confidentiality label in source",
            "points": 15,
            "source": "rule",
        })

    if is_ocr:
        score += 10
        evidence_categories.append("ocr_source_uncertainty")
        breakdown.append({
            "label": "OCR source uncertainty margin",
            "points": 10,
            "source": "rule",
        })

    ai_evidence_map = [
        ("security_controls", 15, "Security controls described"),
        ("customer_data", 15, "Customer data described"),
        ("legal_financial", 15, "Financial, legal or regulated data"),
        ("proprietary_process", 10, "Proprietary business process"),
    ]
    for key, pts, desc in ai_evidence_map:
        if ai_advisory.get(key) is True:
            score += pts
            evidence_categories.append(key)
            breakdown.append({"label": desc, "points": pts, "source": "ai_evidence"})

    deterministic_score = min(100, score)
    rule_level = score_to_tier(deterministic_score)

    raw_ai_suggested = str(ai_advisory.get("suggested_level", rule_level)).upper()
    ai_suggested_level = raw_ai_suggested if raw_ai_suggested in TIER_ORDER else rule_level

    rule_rank = TIER_ORDER[rule_level]
    ai_rank = TIER_ORDER[ai_suggested_level]
    
    if ai_rank > rule_rank:
        tier_floors = {"L1": 21, "L2": 51, "L3": 76}
        floor_score = tier_floors.get(ai_suggested_level, deterministic_score)
        if floor_score > deterministic_score:
            raised_pts = floor_score - deterministic_score
            deterministic_score = floor_score
            breakdown.append({
                "label": f"Raised to AI-suggested {ai_suggested_level} floor",
                "points": raised_pts,
                "source": "conservative_rule",
            })
        final_level = ai_suggested_level
    else:
        final_level = rule_level

    conflict = (rule_level != ai_suggested_level)
    requires_security_reviewer = (deterministic_score >= 60 or final_level in ("L2", "L3"))

    return {
        "score": deterministic_score,
        "level": final_level,
        "level_label": TIER_LABELS[final_level],
        "rule_level": rule_level,
        "ai_suggested_level": ai_suggested_level,
        "conflict": conflict,
        "evidence_categories": evidence_categories,
        "breakdown": breakdown,
        "quarantine_triggered": quarantine_triggered,
        "requires_security_reviewer": requires_security_reviewer,
        "review_deadline_hours": 24 if final_level in ("L2", "L3") else 48,
    }


__all__ = [
    "compute_confidentiality_score",
    "score_to_tier",
    "TIER_ORDER",
    "TIER_LABELS",
    "INFRASTRUCTURE_PATTERNS",
    "CONFIDENTIAL_LABEL_PATTERN",
]
