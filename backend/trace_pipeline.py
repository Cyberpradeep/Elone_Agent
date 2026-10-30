"""
Elone Agent — Interactive End-to-End SOP Pipeline Tracer & Observability Tool (msg/1.0)
======================================================================================
Implements bus-driven, pure artifact-passing SOP governance tracing under protocol msg/1.0:
  [A1] Ingestion & Parsing      -> Header/magic byte validation, text & segment extraction (Artifact: 'extracted')
  [A3] Security & DLP Sandbox   -> Shannon entropy, secret redaction, AST command sandbox (Artifact: 'security_findings')
  [A2] Structuring Planner      -> Triage classification, Groq JIT converter, OKF steps (Artifacts: 'cleaned', 'canonical_draft')
  [A3] Confidentiality Engine   -> Automated L1/L2/L3 classification scoring (Artifact: 'confidentiality_assessment')
  [A4] Verification Engine      -> Linkage validator, Z.ai faithfulness, Quality Score Q (Artifact: 'quality_report')
  [Correction Loop]             -> Automated A4 -> A2 feedback loop (bounded to max 1 loop per revision)
  [A5] Human Review & Staging   -> Staged in _drafts/, dual-custody review task RT-xxxxxx (Artifact: 'review_task', 'review_decision')
  [A6] Hub & Indexing Engine    -> HMAC signing, disk commit, multi-tenant search indexing (Artifact: 'publication_record')
"""

import os
import sys
import time
import uuid
import hashlib
import argparse
import warnings
from typing import Dict, Any, Optional

warnings.filterwarnings("ignore", message=".*automatic function calling.*")
warnings.filterwarnings("ignore", category=UserWarning, module=".*google.*")

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Import configuration and context
from config.settings import get_settings, get_max_file_size_mb, get_max_images_per_sop
from config.llm_config import print_active_models
from api.context import UPLOADS_DIR, DRAFTS_DIR, SOPS_DIR

# Import msg/1.0 protocol schemas and orchestrator bus
from schemas.protocol_msg import (
    TaskMessage,
    ResultMessage,
    Artifact,
    ALLOWED_ROUTES,
    ARTIFACT_PERMISSIONS,
    AgentProtocolError,
)
from orchestrator.bus import AgentMessageBus, ArtifactStore, MAX_AGENT_CALLS_PER_JOB
from orchestrator.agent_runners import get_retrieval_index

# Import unified Rich pipeline observability helpers
from utils.pipeline_logger import (
    log_pipeline_header,
    log_stage_header,
    log_protocol_dispatch,
    log_protocol_result,
    log_stage1_intake,
    log_stage2_security,
    log_stage3_structuring,
    log_stage4_quality,
    log_stage5_review,
    log_stage6_publication,
    log_pipeline_summary,
    log_info,
    log_warning,
    log_error,
)


def trace_e2e_sop(sop_filepath: str, auto_approve: bool = False, tenant_id: str = "tenant-default"):
    total_start_time = time.time()
    filename = os.path.basename(sop_filepath)

    if not os.path.exists(sop_filepath):
        log_error("Pipeline", f"SOP file '{sop_filepath}' does not exist.")
        return

    # Compute source content hash for immutable tracking (Section 6.1)
    with open(sop_filepath, "rb") as f:
        raw_bytes = f.read()
    content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    correlation_id = f"job-{uuid.uuid4().hex[:12]}"
    initial_sop_id = f"SOP-{os.path.splitext(filename)[0][:18].upper()}"

    log_pipeline_header(filename, content_sha256, correlation_id, tenant_id)
    print_active_models()

    # Initialize Bus & Register Standard Runners
    bus = AgentMessageBus()
    bus.load_standard_runners()

    # Create initial upload artifact
    upload_art = Artifact.create(
        tenant_id=tenant_id,
        artifact_type="upload",
        created_by="orchestrator",
        data={"filepath": os.path.abspath(sop_filepath), "filename": filename, "file_size": len(raw_bytes)},
    )
    bus.artifact_store.put(upload_art)
    log_info("Pipeline", f"Initial Upload Artifact registered: {upload_art.artifact_id} (type: 'upload')")

    # ---------------------------------------------------------------------------
    # STAGE 1: Agent A1 — Intake Security & Document Parsing
    # ---------------------------------------------------------------------------
    log_stage_header(1, "Agent A1: Ingestion", "Intake Validation & Parsing")
    task_a1 = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=initial_sop_id,
        source_version_id=f"{initial_sop_id}@v1",
        source_content_hash=content_sha256,
        sender="orchestrator",
        recipient="A1",
        task_type="extract",
        input_artifact_references=[upload_art.artifact_id],
        idempotency_key=f"{correlation_id}:extract:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a1)
    res_a1 = bus.execute_task(task_a1)
    log_protocol_result(res_a1)

    if res_a1.status != "success":
        log_error("Ingestion", f"Stage 1 Intake failed: {res_a1.structured_findings}")
        return

    extracted_art_ref = res_a1.output_artifact_reference
    extracted_art = bus.artifact_store.get(extracted_art_ref, requesting_tenant=tenant_id)
    raw_text = extracted_art.data.get("raw_text", "")
    segments = extracted_art.data.get("segments", [])
    parser_type = res_a1.structured_findings.get("parser_type", "universal")
    img_segments = [s for s in segments if isinstance(s, dict) and s.get("type") == "image"]

    log_stage1_intake(
        parser_type=parser_type,
        char_count=len(raw_text),
        word_count=len(raw_text.split()),
        line_count=len(raw_text.splitlines()),
        seg_count=len(segments),
        img_count=len(img_segments),
        max_imgs=get_max_images_per_sop(),
        sample_text=raw_text,
    )

    # ---------------------------------------------------------------------------
    # STAGE 2: Agent A3 — Security & DLP Inspection (Secret Gate)
    # ---------------------------------------------------------------------------
    log_stage_header(2, "Agent A3: Security", "DLP Secret Redaction & AST Threat Sandbox")
    task_a3 = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=initial_sop_id,
        source_version_id=f"{initial_sop_id}@v1",
        source_content_hash=content_sha256,
        sender="orchestrator",
        recipient="A3",
        task_type="secret_gate",
        input_artifact_references=[extracted_art_ref],
        idempotency_key=f"{correlation_id}:secret_gate:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a3)
    res_a3 = bus.execute_task(task_a3)
    log_protocol_result(res_a3)

    sec_findings_art_ref = res_a3.output_artifact_reference
    sec_data = res_a3.structured_findings
    total_redacted = sec_data.get("total_secrets_detected", 0)
    redaction_counts = sec_data.get("redaction_counts", {})
    ast_count = sec_data.get("ast_threats_count", 0)

    findings_art = bus.artifact_store.get(sec_findings_art_ref, requesting_tenant=tenant_id)
    ast_threats = findings_art.data.get("ast_threats", []) if findings_art else []

    log_stage2_security(
        total_redacted=total_redacted,
        redaction_counts=redaction_counts,
        ast_count=ast_count,
        ast_threats=ast_threats,
        is_quarantined=(res_a3.status == "blocked"),
    )

    if res_a3.status == "blocked":
        log_error("Security Gate", "Stage 2 Secret Gate failed: Pipeline halted at Terminal Quarantine.")
        return

    # ---------------------------------------------------------------------------
    # STAGE 3: Agent A2 — Structuring & JIT Converter
    # ---------------------------------------------------------------------------
    log_stage_header(3, "Agent A2: Structuring", "Triage Routing & JIT Playbook Planning")
    task_a2 = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=initial_sop_id,
        source_version_id=f"{initial_sop_id}@v1",
        source_content_hash=content_sha256,
        sender="A1",
        recipient="A2",
        task_type="clean_and_structure",
        input_artifact_references=[extracted_art_ref],
        idempotency_key=f"{correlation_id}:clean_and_structure:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a2)
    res_a2 = bus.execute_task(task_a2)
    log_protocol_result(res_a2)

    if res_a2.status != "success":
        log_error("Structuring", f"Stage 3 Structuring failed: {res_a2.structured_findings}")
        return

    canonical_art_ref = res_a2.output_artifact_reference
    cleaned_art_ref = res_a2.structured_findings.get("cleaned_artifact_reference")
    canonical_art = bus.artifact_store.get(canonical_art_ref, requesting_tenant=tenant_id)
    canonical_data = canonical_art.data.get("canonical_json", {})
    okf_draft = canonical_art.data.get("okf_draft", {})
    frontmatter = okf_draft.get("frontmatter", {})

    sop_id = canonical_data.get("sop_id") or frontmatter.get("sop_id", initial_sop_id)
    title = canonical_data.get("title") or frontmatter.get("title", "Untitled SOP")
    steps = canonical_data.get("steps") or frontmatter.get("steps", [])

    # Confidentiality Assessment: A2 -> A3 (assess)
    task_a3_conf = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=sop_id,
        source_version_id=f"{sop_id}@v1",
        source_content_hash=content_sha256,
        sender="A2",
        recipient="A3",
        task_type="assess",
        input_artifact_references=[cleaned_art_ref, sec_findings_art_ref],
        idempotency_key=f"{correlation_id}:assess:v1:rev1:loop0",
    )
    res_a3_conf = bus.execute_task(task_a3_conf)
    conf_assessment_art_ref = res_a3_conf.output_artifact_reference
    conf_tier = res_a3_conf.structured_findings.get("classification_level", "L1")
    conf_score = res_a3_conf.structured_findings.get("confidentiality_score", 0)

    log_stage3_structuring(
        sop_id=sop_id,
        title=title,
        platform=frontmatter.get("platform", "system"),
        target_os=frontmatter.get("target_os", "windows"),
        step_count=len(steps),
        conf_tier=conf_tier,
        conf_score=conf_score,
    )

    # ---------------------------------------------------------------------------
    # STAGE 4: Agent A4 — Verification & Governance Quality Scoring
    # ---------------------------------------------------------------------------
    log_stage_header(4, "Agent A4: Verification", "Faithfulness, Quote Tracing & Quality Scoring")
    task_a4 = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=sop_id,
        source_version_id=f"{sop_id}@v1",
        source_content_hash=content_sha256,
        sender="A2",
        recipient="A4",
        task_type="verify",
        input_artifact_references=[cleaned_art_ref, canonical_art_ref, sec_findings_art_ref],
        idempotency_key=f"{correlation_id}:verify:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a4)
    res_a4 = bus.execute_task(task_a4)
    log_protocol_result(res_a4)

    q_data = res_a4.structured_findings
    completeness = q_data.get("completeness", 0.0)
    traceability = q_data.get("traceability", 0.0)
    q_score = q_data.get("quality_score", 0.0)
    q_status = q_data.get("status", "pending")
    blocking_count = q_data.get("blocking_issues_count", 0)

    log_stage4_quality(
        completeness=completeness,
        traceability=traceability,
        blocking_count=blocking_count,
        q_score=q_score,
        q_status=q_status,
        unresolved_issues=res_a4.unresolved_issues,
        quotes_verified=q_data.get("verified_quotes"),
        total_quotes=q_data.get("total_quotes"),
    )

    # ---------------------------------------------------------------------------
    # PROTOCOL FEATURE: Item D — Automated A4 -> A2 Correction Loop (Max 1 Loop)
    # ---------------------------------------------------------------------------
    if (res_a4.status == "needs_review" or blocking_count > 0) and res_a4.unresolved_issues:
        log_warning("Correction Loop", f"Verification flagged {len(res_a4.unresolved_issues)} issue(s). Dispatching bounded A4 -> A2 task...")

        task_corr = TaskMessage(
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            sop_id=sop_id,
            source_version_id=f"{sop_id}@v1",
            source_content_hash=content_sha256,
            sender="A4",
            recipient="A2",
            task_type="correct",
            input_artifact_references=[extracted_art_ref, res_a4.output_artifact_reference],
            requested_operation={"errors": [iss.get("error") for iss in res_a4.unresolved_issues]},
            idempotency_key=f"{correlation_id}:correct:v1:rev1:loop1",
        )
        log_protocol_dispatch(task_corr)
        res_a2_corr = bus.execute_task(task_corr)
        log_protocol_result(res_a2_corr)

        if res_a2_corr.status == "success":
            canonical_art_ref = res_a2_corr.output_artifact_reference
            cleaned_art_ref = res_a2_corr.structured_findings.get("cleaned_artifact_reference", cleaned_art_ref)
            log_info("Correction Loop", "Correction accepted. Running deterministic re-verification: A2 -> A4...")

            task_reverify = TaskMessage(
                correlation_id=correlation_id,
                tenant_id=tenant_id,
                sop_id=sop_id,
                source_version_id=f"{sop_id}@v1",
                source_content_hash=content_sha256,
                sender="A2",
                recipient="A4",
                task_type="verify",
                input_artifact_references=[cleaned_art_ref, canonical_art_ref, sec_findings_art_ref],
                idempotency_key=f"{correlation_id}:reverify:v1:rev1:loop1",
            )
            res_a4 = bus.execute_task(task_reverify)
            log_protocol_result(res_a4)
            q_data = res_a4.structured_findings
            q_score = q_data.get("quality_score", q_score)
            log_info("Correction Loop", f"Post-Correction Governance Score: {q_score:.1f} / 100.0 (Status: {res_a4.status})")

    # ---------------------------------------------------------------------------
    # STAGE 5: Agent A5 — Review & Staging (Human-in-the-Loop)
    # ---------------------------------------------------------------------------
    log_stage_header(5, "Agent A5: HITL Review", "Dual-Custody Staging & Review Task Registration")
    task_a5_stage = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=sop_id,
        source_version_id=f"{sop_id}@v1",
        source_content_hash=content_sha256,
        sender="orchestrator",
        recipient="A5",
        task_type="create_task",
        input_artifact_references=[canonical_art_ref, res_a4.output_artifact_reference, conf_assessment_art_ref],
        idempotency_key=f"{correlation_id}:create_task:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a5_stage)
    res_a5_stage = bus.execute_task(task_a5_stage)
    log_protocol_result(res_a5_stage)

    rt_data = res_a5_stage.structured_findings
    log_stage5_review(
        draft_file=str(rt_data.get("draft_file")),
        review_task_id=str(rt_data.get("review_task_id")),
        assigned_role=str(rt_data.get("assigned_role")),
        due_date=str(rt_data.get("due_date")),
    )

    # Interactive Human Decision Gate
    decision = "approve"
    if not auto_approve:
        print()
        log_warning("HITL Gate", f"The SOP '{title}' [{sop_id}] is staged and awaiting your governance decision.")
        user_input = input("  Enter decision [A]pprove & Publish / [R]eject / [E]xit without publish: ").strip().lower()
        if user_input.startswith("a"):
            decision = "approve"
        elif user_input.startswith("r"):
            decision = "reject"
        else:
            log_info("HITL Gate", "Draft remains safely staged in _drafts/ awaiting future approval.")
            return

    # Record Decision via Agent A5 Runner
    task_a5_decision = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=sop_id,
        source_version_id=f"{sop_id}@v1",
        source_content_hash=content_sha256,
        sender="orchestrator",
        recipient="A5",
        task_type="record_decision",
        input_artifact_references=[canonical_art_ref],
        requested_operation={
            "decision": decision,
            "reviewer": "human.reviewer@governance.corp",
            "uploaded_by": "author@corp.com",
            "actor_type": "human",
        },
        idempotency_key=f"{correlation_id}:record_decision:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a5_decision)
    res_a5_decision = bus.execute_task(task_a5_decision)
    log_protocol_result(res_a5_decision)

    if decision == "reject" or res_a5_decision.status != "success":
        log_warning("Review Gate", "Decision is REJECT. SOP will remain quarantined.")
        return

    review_decision_art_ref = res_a5_decision.output_artifact_reference

    # ---------------------------------------------------------------------------
    # STAGE 6: Agent A6 — SOP Hub & Downstream Retrieval Indexing
    # ---------------------------------------------------------------------------
    log_stage_header(6, "Agent A6: Hub & Indexer", "Publication Gates, HMAC Signing & Clearance Indexing")
    task_a6 = TaskMessage(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        sop_id=sop_id,
        source_version_id=f"{sop_id}@v1",
        source_content_hash=content_sha256,
        sender="A5",
        recipient="A6",
        task_type="publish",
        input_artifact_references=[canonical_art_ref, review_decision_art_ref],
        idempotency_key=f"{correlation_id}:publish:v1:rev1:loop0",
    )
    log_protocol_dispatch(task_a6)
    res_a6 = bus.execute_task(task_a6)
    log_protocol_result(res_a6)

    if res_a6.status != "success":
        log_error("Publication", f"Stage 6 Publication failed: {res_a6.structured_findings}")
        return

    pub_data = res_a6.structured_findings
    sig = pub_data.get("hmac_signature") or "N/A"
    log_stage6_publication(
        sop_id=sop_id,
        published_path=str(pub_data.get("published_okf_path")),
        canonical_path=str(pub_data.get("canonical_json_path")),
        hmac_sig=sig,
        verified=bool(pub_data.get("hmac_verified")),
        tenant_id=str(pub_data.get("tenant_id", tenant_id)),
        clearance=str(pub_data.get("clearance_level")),
        citation=str(pub_data.get("citation")),
    )

    # Perform a test verification query
    retrieval_idx = get_retrieval_index()
    query_word = "terminate" if "kill" in sop_id.lower() or "terminate" in title.lower() else "user"
    results = retrieval_idx.search(
        query=query_word,
        tenant_id=pub_data.get("tenant_id", tenant_id),
        clearance_level=pub_data.get("clearance_level", "L1"),
        limit=3
    )
    log_info("Downstream Catalog", f"Verification Query '{query_word}' -> Found {len(results)} matching SOP(s)")

    # ---------------------------------------------------------------------------
    # OVERALL PIPELINE SUMMARY & OBSERVABILITY
    # ---------------------------------------------------------------------------
    total_elapsed = time.time() - total_start_time
    budget = bus.get_job_budget(correlation_id)

    log_pipeline_summary(
        filename=filename,
        sop_id=sop_id,
        elapsed=total_elapsed,
        msg_count=len(bus.get_log(limit=100)),
        calls=budget["agent_calls"],
        max_calls=MAX_AGENT_CALLS_PER_JOB,
        playbook_path=str(pub_data.get("published_okf_path")),
        canonical_path=str(pub_data.get("canonical_json_path")),
        status="PUBLISHED & RETRIEVABLE",
    )


def main():
    parser = argparse.ArgumentParser(description="Trace an SOP through all 6 agents end-to-end under msg/1.0 protocol")
    parser.add_argument("--file", type=str, help="Path to SOP file (.pdf, .docx, .txt)")
    parser.add_argument("--sample", type=str, choices=["windows_kill", "password_reset", "vpn", "custom"], help="Quick sample selector")
    parser.add_argument("--auto-approve", action="store_true", help="Automatically approve without prompt")
    parser.add_argument("--tenant", type=str, default="tenant-default", help="Tenant ID for multi-tenant isolation")

    args = parser.parse_args()

    samples = {
        "windows_kill": os.path.join(UPLOADS_DIR, "SOP_Kill_Hang_Application_Windows.pdf"),
        "password_reset": os.path.join(UPLOADS_DIR, "solndra_password_reset.docx"),
        "vpn": os.path.join(UPLOADS_DIR, "ARVpndetails.docx"),
    }

    sop_file = None
    if args.file:
        sop_file = args.file
    elif args.sample and args.sample in samples:
        sop_file = samples[args.sample]
    else:
        print("\nSelect an SOP to trace end-to-end:\n")
        print("  1. Windows Kill Hang Application (PDF)       -> [Command Workflow]")
        print("  2. Solandra User Password Reset (DOCX)       -> [API Tool Call Workflow]")
        print("  3. AirRetailer VPN Connection (DOCX)         -> [VPN / Network Workflow]")
        print("  4. Quick In-Memory Text SOP                  -> [Instant Test]")
        print("  5. Specify a Custom File Path")

        choice = input("\nEnter choice (1-5, default 1): ").strip()
        if choice == "2":
            sop_file = samples["password_reset"]
        elif choice == "3":
            sop_file = samples["vpn"]
        elif choice == "4":
            temp_path = os.path.join(UPLOADS_DIR, "quick_trace_restart_service.txt")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("""Standard Operating Procedure: Restart Web Application Service
1. Open PowerShell or Terminal with administrative privileges.
2. Check current service status using 'systemctl status nginx'.
3. Restart the service by running 'systemctl restart nginx'.
4. Confirm service is active and listening on port 80/443.
5. In case of failure, check logs with 'journalctl -u nginx --no-pager -n 50'.""")
            sop_file = temp_path
        elif choice == "5":
            sop_file = input("Enter full path to SOP file: ").strip()
        else:
            sop_file = samples["windows_kill"]

    if not os.path.exists(sop_file):
        log_error("CLI", f"SOP file '{sop_file}' does not exist.")
        sys.exit(1)

    trace_e2e_sop(sop_file, auto_approve=args.auto_approve, tenant_id=args.tenant)


if __name__ == "__main__":
    main()
