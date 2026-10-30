"""
Agent Protocol msg/1.0 Standard Runners
========================================
Implements Section 5 & 6 of SOP Governance Hub v1.0:
Wraps Agents A1 through A6 into uniform callable protocol runners:
    runner(task: TaskMessage, bus: AgentMessageBus) -> ResultMessage

Enforces:
1. Pure artifact input/output by reference via bus.artifact_store.
2. Tenant matching and role-based read/write artifact type validation.
3. Structured findings, error codes, and metrics reporting.
"""

import os
import time
import json
import hashlib
import datetime
from typing import Dict, Any, Optional, List, Callable

from schemas.protocol_msg import (
    TaskMessage,
    ResultMessage,
    Artifact,
    AgentProtocolError,
    TenantMismatchError,
    ArtifactAccessDeniedError,
)

# Domain agent imports
from agents.a1_ingestion.intake_validator import validate_sop_file
from agents.a1_ingestion.document_extractor import extract_ordered_sop_content
from agents.a2_structuring.execution_planner import plan_okf_from_raw
from agents.a2_structuring.canonical_builder import build_canonical_sop_from_draft, write_canonical_sop_json
from agents.a2_structuring.text_cleaner import clean_and_normalize_text
from agents.a3_security.secret_scanner import scan_for_secrets
from utils.security import redact_sensitive_dlp
from agents.a3_security.ast_sandbox import scan_commands_for_ast_threats
from agents.a3_security.confidentiality_engine import compute_confidentiality_score
from agents.a4_verification.plan_validator import validate_plan_faithfulness_and_linkage
from agents.a4_verification.quality_engine import compute_quality_score
from agents.a4_verification.quote_tracer import compute_source_line_coverage
from agents.a5_review.draft_store import stage_unapproved_draft, commit_draft_to_playbook
from agents.a5_review.task_manager import create_review_task
from agents.a5_review.sod_policy import (
    verify_separation_of_duties,
    validate_human_reviewer,
    evaluate_publication_gates,
)
from agents.a6_hub.retrieval_catalog import DownstreamRetrievalIndex
from utils.security import validate_sop_hmac_file

_global_retrieval_index: Optional[DownstreamRetrievalIndex] = None

def get_retrieval_index() -> DownstreamRetrievalIndex:
    global _global_retrieval_index
    if _global_retrieval_index is None:
        _global_retrieval_index = DownstreamRetrievalIndex()
    return _global_retrieval_index


# ---------------------------------------------------------------------------
# Helper: Fetch required input artifact with tenant validation
# ---------------------------------------------------------------------------

def _get_input_artifact(task: TaskMessage, bus: Any, artifact_type: str) -> Artifact:
    """Finds the first input artifact matching artifact_type with tenant verification."""
    for art_id in task.input_artifact_references:
        art = bus.artifact_store.get(art_id, requesting_tenant=task.tenant_id)
        if art and art.artifact_type == artifact_type:
            return art
    raise AgentProtocolError(
        f"Agent '{task.recipient}' missing required input artifact of type '{artifact_type}'",
        error_code="artifact_missing"
    )


# ---------------------------------------------------------------------------
# Agent A1: Ingestion & Extraction Runner
# ---------------------------------------------------------------------------

def run_a1_ingestion(task: TaskMessage, bus: Any) -> ResultMessage:
    """Agent A1: Ingestion & Extraction (Section 5.1).
    Reads: 'upload' or 'linked_file' artifact.
    Writes: 'extracted' artifact.
    """
    t0 = time.time()
    # 1. Fetch upload artifact
    try:
        upload_art = _get_input_artifact(task, bus, "upload")
    except AgentProtocolError:
        upload_art = _get_input_artifact(task, bus, "linked_file")

    upload_data = upload_art.data
    filepath = upload_data.get("filepath") if isinstance(upload_data, dict) else str(upload_data)
    if not filepath or not os.path.exists(filepath):
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A1",
            status="failed",
            error_code="artifact_missing",
            structured_findings={"error": f"Upload file not found on disk: {filepath}"},
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
        )

    # 2. Intake Gate 1 Validation
    try:
        is_valid, err_msg, intake_meta = validate_sop_file(filepath)
        if not is_valid:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                agent_id="A1",
                status="blocked",
                error_code="signature_mismatch" if "magic" in str(err_msg).lower() else "type_not_allowed",
                structured_findings={"error": str(err_msg)},
                processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
            )
    except Exception as e:
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A1",
            status="blocked",
            error_code="signature_mismatch" if "magic" in str(e).lower() else "type_not_allowed",
            structured_findings={"error": str(e)},
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
        )

    # 3. Document order parsing & extraction
    try:
        parser_type, segments = extract_ordered_sop_content(filepath)
        raw_text = "\n\n".join(seg.get("content", "") for seg in segments if isinstance(seg, dict) and seg.get("content"))
        non_blank_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    except Exception as parse_err:
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A1",
            status="failed",
            error_code="no_text",
            structured_findings={"error": f"Parsing failed: {parse_err}"},
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
        )

    # 4. Store 'extracted' artifact
    clean_segments = []
    for s in segments:
        if isinstance(s, dict):
            item = dict(s)
            if "bytes" in item:
                item["bytes_length"] = len(item.pop("bytes"))
            clean_segments.append(item)
        else:
            clean_segments.append(s)

    extracted_payload = {
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "parser_type": parser_type,
        "segments": clean_segments,
        "raw_text": raw_text,
        "total_chars": len(raw_text),
        "total_lines": len(non_blank_lines),
        "intake_meta": intake_meta,
    }
    extracted_art = Artifact.create(
        tenant_id=task.tenant_id,
        artifact_type="extracted",
        created_by="A1",
        data=extracted_payload,
    )
    bus.artifact_store.put(extracted_art)

    return ResultMessage(
        task_id=task.task_id,
        correlation_id=task.correlation_id,
        agent_id="A1",
        status="success",
        output_artifact_reference=extracted_art.artifact_id,
        structured_findings={
            "parser_type": parser_type,
            "total_chars": len(raw_text),
            "total_lines": len(non_blank_lines),
            "segments_count": len(segments),
        },
        source_evidence_references=[f"Lines 1..{len(non_blank_lines)}"],
        processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["file.sniff", "parse.universal"]},
    )


# ---------------------------------------------------------------------------
# Agent A3: Security & Confidentiality Runner
# ---------------------------------------------------------------------------

def run_a3_security(task: TaskMessage, bus: Any) -> ResultMessage:
    """Agent A3: Security & Confidentiality (Section 5.3).
    Operations:
      - 'secret_gate': Reads 'extracted', writes 'security_findings'. Live secrets trigger terminal quarantine.
      - 'assess': Reads 'cleaned', writes 'confidentiality_assessment'.
    """
    t0 = time.time()

    if task.task_type == "secret_gate":
        extracted_art = _get_input_artifact(task, bus, "extracted")
        raw_text = extracted_art.data.get("raw_text", "")

        # 1. DLP Scan
        sanitized_text, redaction_counts = redact_sensitive_dlp(raw_text)
        crit_secrets = sum(redaction_counts.get(k, 0) for k in ("passwords", "api_keys", "private_keys")) if isinstance(redaction_counts, dict) else 0
        total_redacted = sum(redaction_counts.values()) if isinstance(redaction_counts, dict) else (redaction_counts or 0)

        # 2. AST Sandbox scan for candidate commands
        sample_cmds = [line.strip() for line in raw_text.splitlines() if line.strip().startswith(("rm ", "del ", "taskkill", "powershell", "systemctl", "curl"))]
        threats = scan_commands_for_ast_threats(sample_cmds) if sample_cmds else []

        findings_payload = {
            "total_secrets_detected": crit_secrets,
            "total_redacted_count": total_redacted,
            "redaction_counts": redaction_counts,
            "sanitized_text": sanitized_text,
            "ast_threats": threats,
            "has_threats": len(threats) > 0,
        }
        findings_art = Artifact.create(
            tenant_id=task.tenant_id,
            artifact_type="security_findings",
            created_by="A3",
            data=findings_payload,
        )
        bus.artifact_store.put(findings_art)

        # Secret Gate Policy: If live credential detected, terminal quarantine (Section 10)
        is_blocked = crit_secrets > 0 or task.requested_operation.get("strict_quarantine_on_secret", False)

        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A3",
            status="blocked" if is_blocked else "success",
            error_code="secret_detected" if is_blocked else None,
            output_artifact_reference=findings_art.artifact_id,
            structured_findings={
                "total_secrets_detected": crit_secrets,
                "total_redacted_count": total_redacted,
                "redaction_counts": redaction_counts,
                "ast_threats_count": len(threats),
                "is_quarantined": is_blocked,
            },
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["scan.secrets", "scan.ast"]},
        )

    elif task.task_type in ("assess", "confidentiality_assessment"):
        cleaned_art = _get_input_artifact(task, bus, "cleaned")
        cleaned_text = cleaned_art.data.get("cleaned_text", "")

        # Optional security findings
        sec_findings = {}
        for art_id in task.input_artifact_references:
            a = bus.artifact_store.get(art_id, requesting_tenant=task.tenant_id)
            if a and a.artifact_type == "security_findings":
                sec_findings = a.data
                break

        dlp_counts = sec_findings.get("redaction_counts", {})
        conf_eval = compute_confidentiality_score(cleaned_text, dlp_stats=dlp_counts)

        assessment_art = Artifact.create(
            tenant_id=task.tenant_id,
            artifact_type="confidentiality_assessment",
            created_by="A3",
            data=conf_eval,
        )
        bus.artifact_store.put(assessment_art)

        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A3",
            status="success",
            output_artifact_reference=assessment_art.artifact_id,
            structured_findings={
                "confidentiality_score": conf_eval.get("score"),
                "classification_level": conf_eval.get("level") or conf_eval.get("tier", "L0"),
                "evidence_categories": conf_eval.get("evidence_categories", []),
            },
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["policy.classify"]},
        )

    else:
        raise AgentProtocolError(f"Unsupported task_type '{task.task_type}' for Agent A3", "malformed_task")


# ---------------------------------------------------------------------------
# Agent A2: Cleaning & Structuring Runner
# ---------------------------------------------------------------------------

def run_a2_structuring(task: TaskMessage, bus: Any) -> ResultMessage:
    """Agent A2: Cleaning & Structuring (Section 5.2).
    Operations:
      - 'clean_and_structure': Reads 'extracted', produces 'cleaned' and 'canonical_draft'.
      - 'correct': Reads 'extracted' and 'quality_report', re-synthesizes draft with feedback.
    """
    t0 = time.time()
    extracted_art = _get_input_artifact(task, bus, "extracted")
    filepath = extracted_art.data.get("filepath", "")
    raw_text = extracted_art.data.get("raw_text", "")

    # Check for correction feedback
    feedback_errors = []
    if task.task_type == "correct":
        try:
            qr_art = _get_input_artifact(task, bus, "quality_report")
            qr_data = qr_art.data
            feedback_errors = qr_data.get("validation_errors") or task.requested_operation.get("errors") or []
        except AgentProtocolError:
            feedback_errors = task.requested_operation.get("errors") or []

    # 1. Cleaned text representation (Rules WS-01, HF-01, HF-02)
    cleaned_text, transformations = clean_and_normalize_text(raw_text)
    cleaned_lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]

    cleaned_art = Artifact.create(
        tenant_id=task.tenant_id,
        artifact_type="cleaned",
        created_by="A2",
        data={
            "cleaned_text": cleaned_text,
            "lines_count": len(cleaned_lines),
            "transformations": transformations,
        },
    )
    bus.artifact_store.put(cleaned_art)

    # 2. Synthesis of OKF Draft Playbook & Canonical SOP JSON
    try:
        # pyrefly: ignore [missing-import]
        draft = plan_okf_from_raw(filepath, feedback_override=feedback_errors if feedback_errors else None)
        # 2. Synthesis of OKF Draft Playbook & Canonical SOP JSON with real source metadata
        intake_meta = extracted_art.data.get("intake_meta", {}) if isinstance(extracted_art.data, dict) else {}
        if isinstance(intake_meta, (tuple, list)):
            intake_meta = intake_meta[2] if len(intake_meta) > 2 and isinstance(intake_meta[2], dict) else {}
        elif not isinstance(intake_meta, dict):
            intake_meta = {}
        source_meta = {
            "filename": extracted_art.data.get("filename", os.path.basename(filepath)),
            "detected_type": intake_meta.get("detected_type") or extracted_art.data.get("parser_type"),
            "page_count": intake_meta.get("page_count", 1),
            "size_bytes": intake_meta.get("file_size_bytes") or (os.path.getsize(filepath) if filepath and os.path.exists(filepath) else len(raw_text.encode("utf-8"))),
            "is_ocr": intake_meta.get("is_ocr", False),
        }
        canonical_dict = build_canonical_sop_from_draft(
            draft,
            raw_text=cleaned_text,
            tenant_id=task.tenant_id,
            uploaded_by=task.requested_operation.get("uploaded_by", "author@corp.com"),
            source_metadata=source_meta,
            transformations=transformations,
        )
    except Exception as conv_err:
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A2",
            status="failed",
            error_code="invalid_json",
            structured_findings={"error": f"Structuring failed: {conv_err}"},
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
        )

    canonical_payload = {
        "okf_draft": draft,
        "canonical_json": canonical_dict,
        "sop_id": canonical_dict.get("sop_id"),
        "title": canonical_dict.get("title"),
        "cleaned_artifact_reference": cleaned_art.artifact_id,
    }
    canonical_art = Artifact.create(
        tenant_id=task.tenant_id,
        artifact_type="canonical_draft",
        created_by="A2",
        data=canonical_payload,
    )
    bus.artifact_store.put(canonical_art)

    return ResultMessage(
        task_id=task.task_id,
        correlation_id=task.correlation_id,
        agent_id="A2",
        status="success",
        output_artifact_reference=canonical_art.artifact_id,
        structured_findings={
            "sop_id": canonical_dict.get("sop_id"),
            "title": canonical_dict.get("title"),
            "steps_count": len(canonical_dict.get("steps", [])),
            "cleaned_artifact_reference": cleaned_art.artifact_id,
        },
        processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["normalize.text", "llm.structure"]},
    )


# ---------------------------------------------------------------------------
# Agent A4: Quality & Verification Runner
# ---------------------------------------------------------------------------

def run_a4_verification(task: TaskMessage, bus: Any) -> ResultMessage:
    """Agent A4: Quality & Verification (Section 5.4).
    Reads: 'cleaned' and 'canonical_draft' artifacts.
    Writes: 'quality_report' artifact.
    """
    t0 = time.time()
    cleaned_art = _get_input_artifact(task, bus, "cleaned")
    canonical_art = _get_input_artifact(task, bus, "canonical_draft")

    cleaned_text = cleaned_art.data.get("cleaned_text", "")
    canonical_data = canonical_art.data.get("canonical_json", canonical_art.data)
    okf_draft = canonical_art.data.get("okf_draft", {})
    frontmatter = okf_draft.get("frontmatter", okf_draft)

    # 1. Faithfulness & Schema Linkage Validation
    is_faithful, faith_errors = validate_plan_faithfulness_and_linkage(cleaned_text, frontmatter)

    # 2. Quality Formula: Q = 0.4C + 0.4T + 20 - 5B (with real line coverage accounting)
    raw_lines = cleaned_text.splitlines()
    steps = canonical_data.get("steps") or frontmatter.get("steps") or []
    coverage_items = frontmatter.get("source_action_coverage") or []
    metadata_fields = [
        frontmatter.get("title"),
        frontmatter.get("category"),
        frontmatter.get("target_os"),
        frontmatter.get("platform"),
        frontmatter.get("description"),
        canonical_data.get("purpose", {}).get("text") if isinstance(canonical_data.get("purpose"), dict) else "",
        canonical_data.get("scope", {}).get("text") if isinstance(canonical_data.get("scope"), dict) else "",
        canonical_data.get("owner", {}).get("value") if isinstance(canonical_data.get("owner"), dict) else "",
        canonical_data.get("review_date", {}).get("value") if isinstance(canonical_data.get("review_date"), dict) else "",
    ]
    if isinstance(frontmatter.get("trigger_words"), list):
        metadata_fields.extend(frontmatter.get("trigger_words"))
    if isinstance(canonical_data.get("notes"), list):
        for n in canonical_data.get("notes"):
            if isinstance(n, dict):
                metadata_fields.append(n.get("text", ""))
    if isinstance(canonical_data.get("preconditions"), list):
        for p in canonical_data["preconditions"]:
            metadata_fields.append(p.get("text", "") if isinstance(p, dict) else str(p))
    if isinstance(canonical_data.get("exceptions"), list):
        for e in canonical_data["exceptions"]:
            metadata_fields.append(f"{e.get('condition', '')} {e.get('action', '')}" if isinstance(e, dict) else str(e))

    total_non_blank, mapped_source_lines, mapped_indices = compute_source_line_coverage(
        raw_lines=raw_lines,
        steps=steps,
        coverage_items=coverage_items,
        metadata_fields=metadata_fields,
    )
    total_quotes = max(1, len(steps))
    verified_quotes = total_quotes if is_faithful else max(0, total_quotes - len(faith_errors))

    q_res = compute_quality_score(
        total_non_blank_lines=total_non_blank,
        mapped_source_lines=mapped_source_lines,
        total_quotes=total_quotes,
        verified_quotes=verified_quotes,
        schema_valid=is_faithful,
        blocking_issues_count=len(faith_errors),
    )

    quality_report = {
        "is_faithful": is_faithful,
        "validation_errors": faith_errors,
        "completeness": q_res["completeness"],
        "traceability": q_res["traceability"],
        "quality_score": q_res["quality_score"],
        "status": q_res["status"],
        "blocking_issues_count": len(faith_errors),
        "total_quotes": total_quotes,
        "verified_quotes": verified_quotes,
    }

    qr_art = Artifact.create(
        tenant_id=task.tenant_id,
        artifact_type="quality_report",
        created_by="A4",
        data=quality_report,
    )
    bus.artifact_store.put(qr_art)

    # Determine status per Section 12: if errors exist -> needs_review
    status = "success" if (is_faithful and len(faith_errors) == 0 and q_res["quality_score"] >= 75.0) else "needs_review"

    return ResultMessage(
        task_id=task.task_id,
        correlation_id=task.correlation_id,
        agent_id="A4",
        status=status,
        output_artifact_reference=qr_art.artifact_id,
        structured_findings=q_res,
        unresolved_issues=[{"error": e, "severity": "high"} for e in faith_errors],
        processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["schema.validate", "trace.quotes", "coverage.lines"]},
    )


# ---------------------------------------------------------------------------
# Agent A5: Review & Approval Coordinator Runner
# ---------------------------------------------------------------------------

def run_a5_review(task: TaskMessage, bus: Any) -> ResultMessage:
    """Agent A5: Review & Approval Coordinator (Section 5.5).
    Operations:
      - 'create_task': Stages unapproved draft & registers human review task.
      - 'record_decision': Enforces SoD, human check, and records approval.
    """
    t0 = time.time()
    canonical_art = _get_input_artifact(task, bus, "canonical_draft")
    canonical_data = canonical_art.data.get("canonical_json", canonical_art.data)
    okf_draft = canonical_art.data.get("okf_draft", {})
    sop_id = canonical_data.get("sop_id", "SOP-DRAFT")

    if task.task_type == "create_task":
        # 1. Stage unapproved draft
        draft_file = stage_unapproved_draft(
            sop_id=sop_id,
            draft_data=okf_draft,
            canonical_draft=canonical_data,
            raw_filename=f"{sop_id}.md",
        )

        # 2. Get confidentiality score from input artifacts if available
        conf_score = 15
        conf_level = "L1"
        for art_id in task.input_artifact_references:
            a = bus.artifact_store.get(art_id, requesting_tenant=task.tenant_id)
            if a and a.artifact_type == "confidentiality_assessment":
                conf_score = a.data.get("score", 15)
                conf_level = a.data.get("level") or a.data.get("tier", "L1")
                break

        # 3. Create review task with SLA
        review_task = create_review_task(
            sop_id=sop_id,
            job_id=task.correlation_id,
            version=1,
            content_sha256=task.source_content_hash,
            uploaded_by=task.requested_operation.get("uploaded_by", "author@corp.com"),
            confidentiality_score=conf_score,
            confidentiality_level=conf_level,
        )

        task_payload = {
            "review_task_id": review_task.task_id,
            "sop_id": sop_id,
            "assigned_role": review_task.assigned_role,
            "due_date": review_task.due_date,
            "draft_file": draft_file,
            "confidentiality_level": conf_level,
        }
        rt_art = Artifact.create(
            tenant_id=task.tenant_id,
            artifact_type="review_task",
            created_by="A5",
            data=task_payload,
        )
        bus.artifact_store.put(rt_art)

        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A5",
            status="needs_review",
            output_artifact_reference=rt_art.artifact_id,
            structured_findings=task_payload,
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["review.create_task"]},
        )

    elif task.task_type == "record_decision":
        # Enforce Separation of Duties & Non-negotiable Human Check (Section 13)
        decision = task.requested_operation.get("decision", "approve")
        reviewer = task.requested_operation.get("reviewer", "lead@corp.com")
        uploader = task.requested_operation.get("uploaded_by", "author@corp.com")
        actor_type = task.requested_operation.get("actor_type", "human")

        # 1. Actor check
        validate_human_reviewer(actor_type=actor_type)

        # 2. Separation of duties check
        is_sod_valid, sod_err = verify_separation_of_duties(
            uploaded_by=uploader,
            reviewer=reviewer,
            last_editor=task.requested_operation.get("last_editor"),
        )
        if not is_sod_valid:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                agent_id="A5",
                status="blocked",
                error_code="sod_violation",
                structured_findings={"error": sod_err},
                processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
            )

        decision_payload = {
            "sop_id": sop_id,
            "version": 1,
            "decision": decision,
            "reviewer": reviewer,
            "actor_type": actor_type,
            "content_sha256": task.source_content_hash,
            "decision_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        dec_art = Artifact.create(
            tenant_id=task.tenant_id,
            artifact_type="review_decision",
            created_by="A5",
            data=decision_payload,
        )
        bus.artifact_store.put(dec_art)

        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A5",
            status="success" if decision == "approve" else "blocked",
            output_artifact_reference=dec_art.artifact_id,
            structured_findings=decision_payload,
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["review.record_decision"]},
        )

    else:
        raise AgentProtocolError(f"Unsupported task_type '{task.task_type}' for Agent A5", "malformed_task")


# ---------------------------------------------------------------------------
# Agent A6: SOP Hub & Lifecycle Runner
# ---------------------------------------------------------------------------

def run_a6_hub(task: TaskMessage, bus: Any) -> ResultMessage:
    """Agent A6: SOP Hub & Lifecycle (Section 5.6).
    Reads: 'review_decision' and 'canonical_draft' artifacts.
    Evaluates 6 Publication Gates, commits to production, updates retrieval index.
    Writes: 'publication_record' artifact.
    """
    t0 = time.time()
    canonical_art = _get_input_artifact(task, bus, "canonical_draft")
    decision_art = _get_input_artifact(task, bus, "review_decision")

    canonical_data = canonical_art.data.get("canonical_json", canonical_art.data)
    sop_id = canonical_data.get("sop_id", "SOP-DRAFT")
    decision_data = decision_art.data

    if decision_data.get("decision") != "approve":
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A6",
            status="blocked",
            error_code="not_approved",
            structured_findings={"error": f"Cannot publish unapproved SOP (decision: {decision_data.get('decision')})"},
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
        )

    # 1. Evaluate the 6 Publication Gates with verified data from artifacts (Section 9.1)
    quality_meta = canonical_data.get("quality", {})
    class_meta = canonical_data.get("classification", {})
    issues_list = canonical_data.get("issues", [])

    completeness_pct = float(quality_meta.get("completeness", 0.0))
    traceability_pct = float(quality_meta.get("traceability", 0.0))
    schema_valid = bool(quality_meta.get("schema_valid", True))
    blocking_count = int(quality_meta.get("blocking_issues_count", len(issues_list)))

    secrets_count = 0
    is_quarantined = False

    # Extract verified metrics from artifact store for active correlation and tenant
    for art in bus.artifact_store._store.values():
        if getattr(art, "tenant_id", None) == task.tenant_id:
            if getattr(art, "artifact_type", None) == "quality_report":
                qr = getattr(art, "data", {})
                completeness_pct = float(qr.get("completeness", completeness_pct))
                traceability_pct = float(qr.get("traceability", traceability_pct))
                schema_valid = bool(qr.get("is_faithful", qr.get("schema_valid", schema_valid)))
                blocking_count = int(qr.get("blocking_issues_count", blocking_count))
            elif getattr(art, "artifact_type", None) == "security_findings":
                sec = getattr(art, "data", {})
                secrets_count = int(sec.get("total_secrets_detected", 0))
                is_quarantined = bool(sec.get("is_quarantined", False))

    classification_confirmed = decision_data.get("decision") == "approve"
    rule_ai_conflict = bool(class_meta.get("conflict", False)) and not classification_confirmed

    gate_eval = evaluate_publication_gates(
        secrets_count=secrets_count,
        is_quarantined=is_quarantined,
        schema_valid=schema_valid,
        schema_errors_count=blocking_count,
        traceability_pct=traceability_pct,
        completeness_pct=completeness_pct,
        open_blocking_issues_count=blocking_count,
        classification_confirmed=classification_confirmed,
        rule_ai_conflict=rule_ai_conflict,
    )
    if not gate_eval.passed:
        return ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A6",
            status="blocked",
            error_code="gates_failed",
            structured_findings={"failures": gate_eval.failure_reasons, "gates": gate_eval.gates},
            processing_metrics={"latency_ms": int((time.time() - t0) * 1000)},
        )

    # 2. Commit draft to production sops/
    published_okf_path = commit_draft_to_playbook(sop_id)
    canonical_json_path = write_canonical_sop_json(canonical_data)

    # 3. Validate HMAC signature
    is_verified, v_msg, _fm = validate_sop_hmac_file(published_okf_path)

    # 4. Update Downstream Clearance Retrieval Index
    retrieval_index = get_retrieval_index()
    if "lifecycle" not in canonical_data:
        canonical_data["lifecycle"] = {}
    canonical_data["lifecycle"]["state"] = "published"
    indexed_sop = retrieval_index.index_published_sop(canonical_data)

    pub_payload = {
        "sop_id": sop_id,
        "version": 1,
        "published_okf_path": published_okf_path,
        "canonical_json_path": canonical_json_path,
        "hmac_verified": is_verified,
        "hmac_signature": _fm.get("integrity_hmac_sha256"),
        "citation": indexed_sop.citation,
        "tenant_id": indexed_sop.tenant_id,
        "clearance_level": indexed_sop.classification_level,
        "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    pub_art = Artifact.create(
        tenant_id=task.tenant_id,
        artifact_type="publication_record",
        created_by="A6",
        data=pub_payload,
    )
    bus.artifact_store.put(pub_art)

    return ResultMessage(
        task_id=task.task_id,
        correlation_id=task.correlation_id,
        agent_id="A6",
        status="success",
        output_artifact_reference=pub_art.artifact_id,
        structured_findings=pub_payload,
        processing_metrics={"latency_ms": int((time.time() - t0) * 1000), "tools_used": ["policy.publish_check", "index.update"]},
    )


# ---------------------------------------------------------------------------
# Runner Registry
# ---------------------------------------------------------------------------

STANDARD_AGENT_RUNNERS: Dict[str, Callable[[TaskMessage, Any], ResultMessage]] = {
    "A1": run_a1_ingestion,
    "A2": run_a2_structuring,
    "A3": run_a3_security,
    "A4": run_a4_verification,
    "A5": run_a5_review,
    "A6": run_a6_hub,
}
