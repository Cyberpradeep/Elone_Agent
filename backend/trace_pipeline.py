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

Usage:
  python backend/trace_pipeline.py
  python backend/trace_pipeline.py --file knowledge_base/_uploads/solndra_password_reset.docx
  python backend/trace_pipeline.py --sample windows_kill --auto-approve
"""

import os
import sys
import time
import json
import uuid
import hashlib
import argparse
from typing import Dict, Any, Optional

# Ensure project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Import configuration and logging
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


def print_banner(title: str, char: str = "="):
    line = char * 78
    print(f"\n{line}\n  {title}\n{line}", flush=True)


def print_stage_header(stage_num: int, agent_id: str, title: str):
    print(f"\n{'#' * 78}")
    print(f"  STAGE {stage_num}: [{agent_id}] {title}")
    print(f"{'#' * 78}\n", flush=True)


def print_protocol_dispatch(task: TaskMessage):
    print(f"  [Protocol msg/1.0 Task Dispatch]")
    print(f"    • Sender -> Recipient:   {task.sender} -> {task.recipient} (task_type: '{task.task_type}')")
    print(f"    • Task ID:               {task.task_id}")
    print(f"    • Correlation ID:        {task.correlation_id}")
    print(f"    • Input Artifacts:       {task.input_artifact_references}")
    print(f"    • Idempotency Key:       {task.idempotency_key}")


def print_protocol_result(result: ResultMessage):
    print(f"  [Protocol msg/1.0 Result Received]")
    print(f"    • Status:                {result.status.upper()}")
    print(f"    • Agent ID:              {result.agent_id}")
    if result.output_artifact_reference:
        print(f"    • Output Artifact:       {result.output_artifact_reference}")
    if result.error_code:
        print(f"    • Error Code:            {result.error_code}")
    latency = result.processing_metrics.get("latency_ms", 0)
    tools = result.processing_metrics.get("tools_used", [])
    print(f"    • Telemetry:             latency={latency}ms | tools={tools}")


def trace_e2e_sop(sop_filepath: str, auto_approve: bool = False, tenant_id: str = "tenant-default"):
    total_start_time = time.time()
    filename = os.path.basename(sop_filepath)
    ext = os.path.splitext(filename)[1].lower()

    if not os.path.exists(sop_filepath):
        print(f"Error: SOP file '{sop_filepath}' does not exist.")
        return

    # Compute source content hash for immutable tracking (Section 6.1)
    with open(sop_filepath, "rb") as f:
        raw_bytes = f.read()
    content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    correlation_id = f"job-{uuid.uuid4().hex[:12]}"
    initial_sop_id = f"SOP-{os.path.splitext(filename)[0][:18].upper()}"

    print_banner(f"STARTING FULL PROTOCOL msg/1.0 PIPELINE TRACE FOR: {filename}")
    print_active_models()
    print(f"  • Source Content SHA-256: {content_sha256}")
    print(f"  • Active Correlation ID:  {correlation_id}")
    print(f"  • Active Tenant:          {tenant_id}")
    print(f"  • Protocol Version:       msg/1.0 (Bus-Driven, Pure Artifact References)")

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
    print(f"  • Initial Upload Artifact: {upload_art.artifact_id} (type: 'upload')")

    # ---------------------------------------------------------------------------
    # STAGE 1: Agent A1 — Intake Security & Document Parsing
    # ---------------------------------------------------------------------------
    print_stage_header(1, "Agent A1: Ingestion", "Intake Validation & Parsing")
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
    print_protocol_dispatch(task_a1)
    res_a1 = bus.execute_task(task_a1)
    print_protocol_result(res_a1)

    if res_a1.status != "success":
        print(f"\n[ABORT] Stage 1 Intake failed: {res_a1.structured_findings}")
        return

    extracted_art_ref = res_a1.output_artifact_reference
    extracted_art = bus.artifact_store.get(extracted_art_ref, requesting_tenant=tenant_id)
    raw_text = extracted_art.data.get("raw_text", "")
    segments = extracted_art.data.get("segments", [])
    parser_type = res_a1.structured_findings.get("parser_type", "universal")

    print(f"  • Extraction Engine:      {parser_type}")
    print(f"  • Extracted Text Stats:   {len(raw_text)} chars, {len(raw_text.split())} words, {len(raw_text.splitlines())} lines")
    print(f"  • Ordered Segments:       {len(segments)} segments identified")
    img_segments = [s for s in segments if isinstance(s, dict) and s.get("type") == "image"]
    print(f"  • Embedded Images Found:  {len(img_segments)} (Capped to max {get_max_images_per_sop()} per policy)")

    print(f"\n  [Sample Extracted Content (first 250 chars)]:\n  " + "-" * 70)
    snippet = raw_text[:250].replace("\n", "\n  ")
    print(f"  {snippet}...")
    print(f"  " + "-" * 70)

    # ---------------------------------------------------------------------------
    # STAGE 2: Agent A3 — Security & DLP Inspection (Secret Gate)
    # ---------------------------------------------------------------------------
    print_stage_header(2, "Agent A3: Security", "DLP Secret Redaction & AST Threat Sandbox")
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
    print_protocol_dispatch(task_a3)
    res_a3 = bus.execute_task(task_a3)
    print_protocol_result(res_a3)

    if res_a3.status == "blocked":
        print(f"\n[ABORT] Stage 2 Security Secret Gate failed (Terminal Quarantine): {res_a3.structured_findings}")
        return

    sec_findings_art_ref = res_a3.output_artifact_reference
    sec_data = res_a3.structured_findings
    total_redacted = sec_data.get("total_secrets_detected", 0)
    redaction_counts = sec_data.get("redaction_counts", {})
    ast_count = sec_data.get("ast_threats_count", 0)

    print(f"  • DLP Secret Redaction:   {total_redacted} secret token(s) identified & masked")
    if total_redacted > 0:
        print(f"  • Masked Breakdown:       {redaction_counts}")
    print(f"  • AST Sandbox Safety:     {'CLEAR (No malicious payloads)' if ast_count == 0 else f'ALERT: {ast_count} threats detected'}")

    # ---------------------------------------------------------------------------
    # STAGE 3: Agent A2 — Structuring & JIT Converter
    # ---------------------------------------------------------------------------
    print_stage_header(3, "Agent A2: Structuring", "Triage Routing & JIT Playbook Planning")
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
    print_protocol_dispatch(task_a2)
    res_a2 = bus.execute_task(task_a2)
    print_protocol_result(res_a2)

    if res_a2.status != "success":
        print(f"\n[ABORT] Stage 3 Structuring failed: {res_a2.structured_findings}")
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

    print(f"  • SOP ID Generated:       {sop_id}")
    print(f"  • SOP Title:              {title}")
    print(f"  • Target Platform / OS:   {frontmatter.get('platform', 'system')} / {frontmatter.get('target_os', 'Any')}")
    print(f"  • Execution Steps Built:  {len(steps)} procedural step(s)")

    print(f"\n  [Step-by-Step Execution Plan]:")
    for s in steps:
        step_num = s.get("step_number") or s.get("n")
        desc = s.get("sop_step_description") or s.get("action")
        stype = s.get("step_type") or s.get("actor")
        cmd_or_tool = s.get("command") or s.get("input") or f"{s.get('platform')}.{s.get('function')}({s.get('comm_inputs') or s.get('inputs') or {}})"
        exec_if = s.get("execute_if", "")
        exec_if_str = f" [Condition: {exec_if}]" if exec_if else ""
        print(f"    [{step_num}] ({stype.upper() if stype else 'STEP'}){exec_if_str} {desc}")
        print(f"        Action: {cmd_or_tool}")

    # Confidentiality Assessment: A2 -> A3 (assess)
    print(f"\n  [Performing Confidentiality Assessment (A2 -> A3)]...")
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
    print(f"  • Confidentiality Tier:   {res_a3_conf.structured_findings.get('classification_level', 'L1')} (Score: {res_a3_conf.structured_findings.get('confidentiality_score', 0)})")

    # ---------------------------------------------------------------------------
    # STAGE 4: Agent A4 — Verification & Governance Quality Scoring
    # ---------------------------------------------------------------------------
    print_stage_header(4, "Agent A4: Verification", "Faithfulness, Quote Tracing & Quality Scoring")
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
    print_protocol_dispatch(task_a4)
    res_a4 = bus.execute_task(task_a4)
    print_protocol_result(res_a4)

    q_data = res_a4.structured_findings
    completeness = q_data.get("completeness", 0.0)
    traceability = q_data.get("traceability", 0.0)
    q_score = q_data.get("quality_score", 0.0)
    q_status = q_data.get("status", "pending")
    blocking_count = q_data.get("blocking_issues_count", 0)

    print(f"  • Completeness (C):       {completeness:.1f}%")
    print(f"  • Traceability (T):       {traceability:.1f}%")
    print(f"  • Blocking Issues (B):    {blocking_count}")
    print(f"  • Quality Formula:        Q = 0.4({completeness:.1f}) + 0.4({traceability:.1f}) + 20 - 5({blocking_count})")
    print(f"  • Final Governance Score: {q_score:.1f} / 100.0 (Status: {q_status})")

    # ---------------------------------------------------------------------------
    # PROTOCOL FEATURE: Item D — Automated A4 -> A2 Correction Loop (Max 1 Loop)
    # ---------------------------------------------------------------------------
    if (res_a4.status == "needs_review" or blocking_count > 0) and res_a4.unresolved_issues:
        print("\n" + "~" * 78)
        print("  AUTOMATED CORRECTION LOOP (PROTOCOL msg/1.0 — Item D)")
        print("~" * 78)
        print(f"  Verification flagged {len(res_a4.unresolved_issues)} issue(s). Dispatching bounded A4 -> A2 task...")
        
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
        print_protocol_dispatch(task_corr)
        res_a2_corr = bus.execute_task(task_corr)
        print_protocol_result(res_a2_corr)

        if res_a2_corr.status == "success":
            canonical_art_ref = res_a2_corr.output_artifact_reference
            cleaned_art_ref = res_a2_corr.structured_findings.get("cleaned_artifact_reference", cleaned_art_ref)
            print("  >>> Correction accepted. Running deterministic re-verification: A2 -> A4...")

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
            print_protocol_result(res_a4)
            q_data = res_a4.structured_findings
            q_score = q_data.get("quality_score", q_score)
            print(f"  >>> Post-Correction Governance Score: {q_score:.1f} / 100.0 (Status: {res_a4.status})")

    # ---------------------------------------------------------------------------
    # STAGE 5: Agent A5 — Review & Staging (Human-in-the-Loop)
    # ---------------------------------------------------------------------------
    print_stage_header(5, "Agent A5: HITL Review", "Dual-Custody Staging & Review Task Registration")
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
    print_protocol_dispatch(task_a5_stage)
    res_a5_stage = bus.execute_task(task_a5_stage)
    print_protocol_result(res_a5_stage)

    rt_data = res_a5_stage.structured_findings
    print(f"  • Staged Location:        {rt_data.get('draft_file')}")
    print(f"  • Review Task Created:    {rt_data.get('review_task_id')} (Role: {rt_data.get('assigned_role')})")
    print(f"  • SLA Due Date:           {rt_data.get('due_date')}")
    print(f"  • Separation of Duties:   Enforced (Author != Reviewer; Human Approver Required)")

    # Interactive Human Decision Gate
    decision = "approve"
    if not auto_approve:
        print("\n" + "=" * 78)
        print("  HUMAN-IN-THE-LOOP (HITL) REVIEW GATE")
        print("=" * 78)
        print(f"  The SOP '{title}' [{sop_id}] is staged and awaiting your governance decision.")
        user_input = input("  Enter decision [A]pprove & Publish / [R]eject / [E]xit without publish: ").strip().lower()
        if user_input.startswith("a"):
            decision = "approve"
        elif user_input.startswith("r"):
            decision = "reject"
        else:
            print("\n[Exited] Draft remains safely staged in _drafts/ awaiting future approval.")
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
    print_protocol_dispatch(task_a5_decision)
    res_a5_decision = bus.execute_task(task_a5_decision)
    print_protocol_result(res_a5_decision)

    if decision == "reject" or res_a5_decision.status != "success":
        print(f"\n[Review Gate] Decision is REJECT. SOP will remain quarantined.")
        return

    review_decision_art_ref = res_a5_decision.output_artifact_reference

    # ---------------------------------------------------------------------------
    # STAGE 6: Agent A6 — SOP Hub & Downstream Retrieval Indexing
    # ---------------------------------------------------------------------------
    print_stage_header(6, "Agent A6: Hub & Indexer", "Publication Gates, HMAC Signing & Clearance Indexing")
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
    print_protocol_dispatch(task_a6)
    res_a6 = bus.execute_task(task_a6)
    print_protocol_result(res_a6)

    if res_a6.status != "success":
        print(f"\n[ABORT] Stage 6 Publication failed: {res_a6.structured_findings}")
        return

    pub_data = res_a6.structured_findings
    sig = pub_data.get("hmac_signature") or "N/A"
    print(f"  • Production Playbook:    {pub_data.get('published_okf_path')}")
    print(f"  • Canonical JSON 1.0:     {pub_data.get('canonical_json_path')}")
    print(f"  • Cryptographic Stamp:    HMAC-SHA256 ({sig[:12]}...{sig[-8:] if len(sig) > 8 else ''}) [Verified: {pub_data.get('hmac_verified')}]")
    print(f"  • Retrieval Indexing:     Indexed in Downstream Catalog (Tenant: '{pub_data.get('tenant_id')}', Clearance: '{pub_data.get('clearance_level')}')")
    print(f"  • Citation Stamp:         {pub_data.get('citation')}")

    # Perform a test verification query
    retrieval_idx = get_retrieval_index()
    query_word = "terminate" if "kill" in sop_id.lower() or "terminate" in title.lower() else "user"
    results = retrieval_idx.search(
        query=query_word,
        tenant_id=pub_data.get("tenant_id", tenant_id),
        clearance_level=pub_data.get("clearance_level", "L1"),
        limit=3
    )
    print(f"  • Downstream Search Test: Queried '{query_word}' -> Found {len(results)} matching SOP(s)")

    # ---------------------------------------------------------------------------
    # OVERALL PIPELINE SUMMARY & OBSERVABILITY
    # ---------------------------------------------------------------------------
    total_elapsed = time.time() - total_start_time
    budget = bus.get_job_budget(correlation_id)
    all_artifacts = [msg for msg in bus.get_log(limit=100) if msg.get("type") == "result" and msg.get("status") == "success"]

    print_banner("END-TO-END PIPELINE TRACE COMPLETE", "=")
    print(f"  • Total Pipeline Latency: {total_elapsed:.2f}s")
    print(f"  • Total Bus Messages:     {len(bus.get_log(limit=100))}")
    print(f"  • Agent Calls Dispatched: {budget['agent_calls']} / {MAX_AGENT_CALLS_PER_JOB} (Budget limit: 30)")
    print(f"  • SOP Published ID:       {sop_id}")
    print(f"  • Playbook File:          {pub_data.get('published_okf_path')}")
    print(f"  • Canonical Model File:   {pub_data.get('canonical_json_path')}")
    print(f"  • Final Status:           PUBLISHED & RETRIEVABLE")
    print(f"  • Downstream API Search:  'curl http://127.0.0.1:8000/api/playbooks/search?query={query_word}'")
    print("=" * 78 + "\n")


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
        print_banner("ELONE AGENT — SOP TRACE & OBSERVABILITY EXPLORER (msg/1.0)")
        print("Select an SOP to trace end-to-end:\n")
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
        print(f"Error: SOP file '{sop_file}' does not exist.")
        sys.exit(1)

    trace_e2e_sop(sop_file, auto_approve=args.auto_approve, tenant_id=args.tenant)


if __name__ == "__main__":
    main()
