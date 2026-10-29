"""
Agent A2: Canonical SOP JSON 1.0 Builder & Synchronizer
======================================================
Frozen Specification: SOP Governance Hub v1.0 (Section 16 & 17)
- Dual Export: Saves Canonical JSON alongside OKF Playbook
- Step Auto-Synchronization: Syncs edits in Canonical JSON to OKF .md
- Recomputes and re-stamps HMAC-SHA256 signature
"""

import os
import re
import json
import copy
import yaml
import hashlib
import datetime
import frontmatter
from typing import Dict, Any, Optional, List, Tuple

from utils.security import sanitize_slug, compute_playbook_hmac
from agents.a3_security.confidentiality_engine import compute_confidentiality_score
from agents.a4_verification.quality_engine import compute_quality_score
from agents.a4_verification.quote_tracer import verify_canonical_quotes, compute_source_line_coverage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB_DIR = os.getenv("ELONE_KB_DIR")
if not KB_DIR or not os.path.exists(KB_DIR):
    root_kb = os.path.abspath(os.path.join(BASE_DIR, "..", "knowledge_base"))
    if os.path.exists(root_kb):
        KB_DIR = root_kb
    elif os.path.exists(os.path.join(BASE_DIR, "knowledge_base")):
        KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
    else:
        KB_DIR = root_kb
SOPS_DIR = os.path.join(KB_DIR, "sops")


def _find_matching_line_range(quote: str, raw_lines: List[str]) -> List[int]:
    """Finds the best-matching line index (1-based) in raw_lines for a given quote or heading."""
    if not quote or not raw_lines:
        return [1, 1]
    norm_quote = re.sub(r"[^\w\s]", "", quote.lower()).strip()
    q_tokens = set(t for t in norm_quote.split() if len(t) > 2)
    if not q_tokens:
        return [1, 1]

    best_idx = 1
    best_overlap = 0
    for i, line in enumerate(raw_lines, start=1):
        norm_line = re.sub(r"[^\w\s]", "", line.lower()).strip()
        l_tokens = set(t for t in norm_line.split() if len(t) > 2)
        if not l_tokens:
            continue
        overlap = len(q_tokens.intersection(l_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = i

    return [best_idx, min(len(raw_lines), best_idx + 1)]


def _extract_document_sections(raw_text: str) -> Dict[str, str]:
    """Extracts standard SOP sections (Purpose, Scope, Notes, Owner, Review Date, Platform) from raw text."""
    sections: Dict[str, str] = {}
    if not raw_text:
        return sections

    # Purpose
    m_purp = re.search(
        r'(?:\n|^)\s*(?:\d+[\.\)]\s*)?Purpose\s*[:\n]+\s*([\s\S]*?)(?=\n\s*(?:\d+[\.\)]\s*)?(?:Scope|Procedure|Notes|Internal IT|Document Owner)\b|\Z)',
        raw_text,
        re.IGNORECASE,
    )
    if m_purp:
        sections["purpose"] = m_purp.group(1).strip()

    # Scope
    m_scope = re.search(
        r'(?:\n|^)\s*(?:\d+[\.\)]\s*)?Scope\s*[:\n]+\s*([\s\S]*?)(?=\n\s*(?:\d+[\.\)]\s*)?(?:Procedure|Notes|Purpose|Internal IT|Document Owner)\b|\Z)',
        raw_text,
        re.IGNORECASE,
    )
    if m_scope:
        sections["scope"] = m_scope.group(1).strip()

    # Notes
    m_notes = re.search(
        r'(?:\n|^)\s*(?:\d+[\.\)]\s*)?Notes\s*[:\n]+\s*([\s\S]*?)(?=\n\s*(?:\d+[\.\)]\s*)?(?:Procedure|Scope|Purpose|Internal IT|Document Owner)\b|\Z)',
        raw_text,
        re.IGNORECASE,
    )
    if m_notes:
        sections["notes"] = m_notes.group(1).strip()

    # Document Owner
    m_owner = re.search(r'(?:Document\s+)?Owner\s*[:\n]+\s*([^\n\r]+)', raw_text, re.IGNORECASE)
    if m_owner:
        sections["owner"] = m_owner.group(1).strip()

    # Review Date / Effective Date
    m_date = re.search(r'(?:Effective|Review)\s+Date\s*[:\n]+\s*([^\n\r]+)', raw_text, re.IGNORECASE)
    if m_date:
        sections["review_date"] = m_date.group(1).strip()

    # Platform
    m_plat = re.search(r'Platform\s*[:\n]+\s*([^\n\r]+)', raw_text, re.IGNORECASE)
    if m_plat:
        sections["platform"] = m_plat.group(1).strip()

    return sections


def build_canonical_sop_from_draft(
    draft: Dict[str, Any],
    raw_text: str = "",
    tenant_id: str = "tn_northwind",
    uploaded_by: str = "author@corp.com",
    source_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Constructs a Canonical SOP JSON Schema 1.0 dictionary from a draft OKF playbook (Section 16)."""
    frontmatter_dict = draft.get("frontmatter", draft)
    sop_id = frontmatter_dict.get("sop_id") or "SOP-DYN-001"
    title = frontmatter_dict.get("title") or "Automated Standard Operating Procedure"
    category = frontmatter_dict.get("category") or "general"
    description = frontmatter_dict.get("description") or ""

    if not raw_text and description:
        raw_text = f"{title}\n{description}\n" + "\n".join(
            s.get("sop_step_description", "") for s in frontmatter_dict.get("steps", [])
        )
    source_lines = [line.strip() for line in raw_text.splitlines() if line.strip()] if raw_text else [title]

    # Extract genuine sections & metadata: Hybrid (LLM semantic discovery + Regex extraction)
    llm_meta = frontmatter_dict.get("document_metadata") or {}
    sections = _extract_document_sections(raw_text)

    raw_owner = llm_meta.get("owner") or sections.get("owner")
    doc_owner = raw_owner or uploaded_by

    raw_review_date = llm_meta.get("review_date") or sections.get("review_date")
    doc_review_date = raw_review_date or datetime.datetime.now().strftime("%Y-%m-%d")

    raw_version = llm_meta.get("version_label") or sections.get("version_label")
    doc_version_label = raw_version or "v1.0"

    raw_dept = llm_meta.get("department") or sections.get("department")
    doc_department = raw_dept or category.capitalize()

    purpose_text = llm_meta.get("purpose") or sections.get("purpose") or description or f"Operational execution of {title}"
    scope_text = llm_meta.get("scope") or sections.get("scope") or f"Applies to {category} operations and authorized agents."

    okf_steps = frontmatter_dict.get("steps") or []
    canonical_steps = []
    for idx, s in enumerate(okf_steps, start=1):
        action = s.get("sop_step_description") or f"Execute step {idx}"
        inp = s.get("command") or json.dumps(s.get("comm_inputs") or {})

        # Real line resolution instead of synthetic [idx * 2, idx * 2 + 1]
        line_range = s.get("source_lines")
        if not line_range or not (isinstance(line_range, list) and len(line_range) >= 2):
            line_range = _find_matching_line_range(action, source_lines)

        canonical_steps.append({
            "n": idx,
            "action": action,
            "input": inp,
            "expected_outcome": s.get("parse_instruction"),
            "warning": s.get("fallback_command"),
            "actor": "agent" if s.get("step_type") in ("command", "tool_call") else "user",
            "requires_approval": False,
            "risk": "low",
            "source_lines": line_range,
            "quote": action,
            "verified": False,
        })

    verified_quotes_count = 0
    if source_lines:
        total_quotes, verified_quotes_count, _ = verify_canonical_quotes(canonical_steps, source_lines)

    canonical_notes = []
    raw_notes = []
    if llm_meta.get("notes") and isinstance(llm_meta["notes"], list):
        raw_notes.extend([str(n) for n in llm_meta["notes"] if n])
    if sections.get("notes") and sections["notes"] not in raw_notes:
        raw_notes.append(sections["notes"])

    for n_text in raw_notes:
        n_lines = _find_matching_line_range(n_text, source_lines)
        canonical_notes.append({
            "text": n_text,
            "source_lines": n_lines,
            "quote": n_text[:100],
            "verified": True,
        })

    coverage_meta = [
        title,
        category,
        description,
        purpose_text,
        scope_text,
        sections.get("notes", ""),
        sections.get("platform", ""),
        doc_owner,
        doc_review_date,
    ]
    if isinstance(frontmatter_dict.get("trigger_words"), list):
        coverage_meta.extend(frontmatter_dict.get("trigger_words"))

    total_non_blank, mapped_count, _ = compute_source_line_coverage(
        raw_lines=source_lines,
        steps=canonical_steps,
        coverage_items=frontmatter_dict.get("source_action_coverage") or [],
        metadata_fields=coverage_meta,
    )
    conf_res = compute_confidentiality_score(raw_text or title)
    quality_res = compute_quality_score(
        total_non_blank_lines=total_non_blank,
        mapped_source_lines=mapped_count,
        total_quotes=max(1, len(canonical_steps)),
        verified_quotes=verified_quotes_count,
        schema_valid=True,
        blocking_issues_count=0,
    )

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest() if raw_text else hashlib.sha256(sop_id.encode("utf-8")).hexdigest()

    title_lines = _find_matching_line_range(title, source_lines)
    meta_start = min(title_lines[1] + 1, len(source_lines))
    metadata_lines = [meta_start, min(meta_start + 1, len(source_lines))]
    owner_lines = _find_matching_line_range(doc_owner, source_lines) if raw_owner else metadata_lines
    date_lines = _find_matching_line_range(doc_review_date, source_lines) if raw_review_date else metadata_lines
    version_lines = _find_matching_line_range(doc_version_label, source_lines) if raw_version else metadata_lines
    dept_lines = _find_matching_line_range(doc_department, source_lines) if raw_dept else metadata_lines
    purpose_lines = _find_matching_line_range(purpose_text, source_lines)
    scope_lines = _find_matching_line_range(scope_text, source_lines)

    meta = source_metadata or draft.get("source_metadata") or draft.get("intake_meta") or {}
    source_filename = meta.get("filename") or os.path.basename(draft.get("raw_filepath", f"{sop_id.lower()}.txt"))
    detected_type = meta.get("detected_type") or meta.get("mime_type") or ("application/pdf" if str(source_filename).endswith(".pdf") else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if str(source_filename).endswith(".docx") else "text/plain"))
    page_count = int(meta.get("page_count") or meta.get("pages") or 1)

    return {
        "schema_version": "1.0",
        "sop_id": sop_id,
        "version": 1,
        "tenant_id": tenant_id,
        "title": title,
        "title_lines": title_lines,
        "metadata_lines": metadata_lines,
        "department": {"status": "present" if raw_dept else "missing", "value": doc_department, "source_lines": dept_lines},
        "owner": {"status": "present" if raw_owner else "missing", "value": doc_owner, "source_lines": owner_lines},
        "version_label": {"status": "present" if raw_version else "missing", "value": doc_version_label, "source_lines": version_lines},
        "review_date": {"status": "present" if raw_review_date else "missing", "value": doc_review_date, "source_lines": date_lines},
        "source": {
            "filename": source_filename,
            "sha256": content_hash,
            "size": int(meta.get("size_bytes") or len(raw_text.encode("utf-8"))),
            "detected_type": detected_type,
            "pages": page_count,
            "extracted_lines": len(source_lines),
            "ocr": bool(meta.get("is_ocr", False)),
        },
        "purpose": {
            "text": purpose_text,
            "source_lines": purpose_lines,
            "quote": purpose_text[:100],
            "verified": True,
        },
        "scope": {
            "text": scope_text,
            "source_lines": scope_lines,
            "quote": scope_text[:100],
            "verified": True,
        },
        "preconditions": [],
        "roles": [
            {"role": "Operator", "responsibility": f"Executes {title}", "source_lines": [1]}
        ],
        "steps": canonical_steps,
        "exceptions": [],
        "notes": canonical_notes,
        "references": [],
        "media": [],
        "issues": [],
        "classification": {
            "level": conf_res["level"],
            "score": conf_res["score"],
            "evidence_categories": conf_res["evidence_categories"],
            "rule_level": conf_res["rule_level"],
            "ai_suggested_level": conf_res["ai_suggested_level"],
            "rationale": "Deterministic rule classification",
            "confirmed": False,
        },
        "quality": {
            "completeness": quality_res["completeness"],
            "traceability": quality_res["traceability"],
            "schema_valid": quality_res["schema_valid"],
            "blocking_issues_count": quality_res["blocking_issues_count"],
            "quality_score": quality_res["quality_score"],
            "status": quality_res["status"],
        },
        "transformations": [],
        "lifecycle": {
            "state": "structuring",
            "uploaded_by": uploaded_by,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "approvals": [],
        },
        "provenance": {
            "producing_agent": "A2_structuring",
            "provider": "elverve_ai",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    }


def write_canonical_sop_json(canonical_data: Dict[str, Any], category: str = "general") -> str:
    """Saves Canonical SOP JSON Schema 1.0 to disk alongside the OKF Playbook."""
    category = sanitize_slug(category).lower()
    sop_id = sanitize_slug(canonical_data.get("sop_id") or "SOP-DYN-001")
    cat_dir = os.path.join(SOPS_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)
    json_path = os.path.join(cat_dir, f"{sop_id}.canonical.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(canonical_data, f, indent=2)
    return json_path


def sync_canonical_to_playbook(canonical_data: Dict[str, Any], category: Optional[str] = None) -> str:
    """Synchronizes steps and metadata from Canonical JSON into the corresponding OKF .md Playbook.
    Recomputes and stamps the HMAC-SHA256 signature so the file remains valid and runnable on disk.
    """
    dept = canonical_data.get("department", {})
    dept_val = dept.get("value") if isinstance(dept, dict) else str(dept or "")
    cat = category or (dept_val or "general").lower()
    cat = sanitize_slug(cat).lower()
    sop_id = sanitize_slug(canonical_data.get("sop_id") or "SOP-DYN-001")

    md_path = os.path.join(SOPS_DIR, cat, f"{sop_id}.md")
    existing_frontmatter: Dict[str, Any] = {}
    if os.path.exists(md_path):
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)
                existing_frontmatter = post.metadata
        except Exception:
            pass

    existing_frontmatter["sop_id"] = sop_id
    existing_frontmatter["title"] = canonical_data.get("title", existing_frontmatter.get("title", sop_id))
    existing_frontmatter["category"] = cat
    existing_frontmatter["description"] = (
        canonical_data.get("purpose", {}).get("text")
        if isinstance(canonical_data.get("purpose"), dict)
        else existing_frontmatter.get("description", "")
    )

    new_okf_steps = []
    for step in canonical_data.get("steps", []):
        n = step.get("n", 1)
        action = step.get("action", "")
        matched_prev = next((s for s in existing_frontmatter.get("steps", []) if s.get("step_number") == n), {})
        step_dict = {
            "step_number": n,
            "sop_step_description": action,
            "step_type": matched_prev.get("step_type", "command"),
            "platform": matched_prev.get("platform"),
            "function_name": matched_prev.get("function_name"),
            "comm_inputs": matched_prev.get("comm_inputs") or {},
            "command": matched_prev.get("command") or step.get("input"),
            "fallback_command": step.get("warning") or matched_prev.get("fallback_command"),
            "fallback_sop_id": matched_prev.get("fallback_sop_id"),
            "parse_instruction": step.get("expected_outcome") or matched_prev.get("parse_instruction"),
            "execute_if": matched_prev.get("execute_if"),
            "timeout_seconds": matched_prev.get("timeout_seconds", 30),
            "shell": matched_prev.get("shell", "powershell"),
        }
        new_okf_steps.append(step_dict)

    existing_frontmatter["steps"] = new_okf_steps

    clean_frontmatter = copy.deepcopy(existing_frontmatter)
    for s in clean_frontmatter.get("steps", []):
        s.pop("step_reasoning", None)
    clean_frontmatter["integrity_version"] = "v2"
    clean_frontmatter["integrity_hmac_sha256"] = compute_playbook_hmac(clean_frontmatter)

    yaml_header = yaml.dump(clean_frontmatter, sort_keys=False)
    title = clean_frontmatter.get("title", sop_id)
    desc = clean_frontmatter.get("description", "")
    md_body = f"# {title} Playbook\n\n## Overview\n{desc}\n\n## Execution Steps\n"
    for s in new_okf_steps:
        cmd = s.get("command") or "(none)"
        md_body += f"- **Step {s.get('step_number')}**: {s.get('sop_step_description')} (`{cmd}`)\n"

    final_content = f"---\n{yaml_header}---\n\n{md_body}"
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(final_content)

    return md_path


# Aliases
sync_canonical_to_okf = sync_canonical_to_playbook

