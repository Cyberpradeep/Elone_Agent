"""
14-State Orchestrator Lifecycle, State Ledger & Governance Gatekeeper
======================================================================
Implements Sections 8, 9, 10, and 13 of SOP Governance Hub v1.0 (Frozen Spec):
1. Ingestion State Machine (Section 8): 14 official lifecycle states, deterministic
   transition enforcement, and terminal state isolation.
2. Secret Quarantine Protocol (Section 10): Immediate terminal halt on credential
   detection, incident ticket generation (INC-xxxxxx), and content purging.
3. Review Task Coordination (Section 5.5 & 13): Creation of bound review tasks (RT-xxxxxx),
   role routing (Process Owner vs Security Reviewer), and SLA deadline enforcement.
4. Separation of Duties (SoD) Gate (Section 13): Enforces uploader != reviewer and
   last_editor != reviewer; rejects automated LLM approvals.
5. Deterministic Publication Gates (Section 9.1): 6-gate verification checklist
   (Secrets, Schema, Traceability >=90%, Completeness >=80%, Issues=0, Human Confirmation).
6. Orchestrator State Ledger: Thread-safe, persistent state management and audit history.
"""

import os
import json
import uuid
import datetime
import threading
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# 1. State Machine Definitions, Exceptions & Data Entities
# ---------------------------------------------------------------------------

from schemas.governance_models import (
    STATE_RECEIVED,
    STATE_EXTRACTING,
    STATE_SCANNING,
    STATE_STRUCTURING,
    STATE_ASSESSING,
    STATE_CORRECTING,
    STATE_AWAITING_REVIEW,
    STATE_CHANGES_REQUESTED,
    STATE_APPROVED,
    STATE_PUBLISHED,
    STATE_DEACTIVATED,
    STATE_ARCHIVED,
    STATE_SOFT_DELETED,
    STATE_QUARANTINED,
    STATE_REJECTED,
    STATE_DUPLICATE,
    STATE_FAILED,
    STATE_BLOCKED,
    ALL_STATES,
    TERMINAL_STATES,
    ALLOWED_TRANSITIONS,
    GovernanceError,
    IllegalTransitionError,
    SeparationOfDutiesViolation,
    NotHumanActorError,
    GateFailureError,
    StaleApprovalError,
    NotApprovedError,
    QuarantineIncident,
    ReviewTask,
    ReviewDecision,
    PublicationGateResult,
    JobRecord,
    generate_incident_id,
    generate_review_task_id,
    _utc_now_iso,
)


# ---------------------------------------------------------------------------
# 4. Import Gatekeeper Policies from Agent A5 Review
# ---------------------------------------------------------------------------

from agents.a5_review.sod_policy import (
    verify_separation_of_duties,
    validate_human_reviewer,
    evaluate_publication_gates,
)


# ---------------------------------------------------------------------------
# 6. Persistent Orchestrator State Ledger
# ---------------------------------------------------------------------------

class OrchestratorLedger:
    """Thread-safe state manager and persistent audit ledger for SOP lifecycles."""

    def __init__(self, ledger_path: Optional[str] = None):
        self.ledger_path = ledger_path
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        if self.ledger_path and os.path.exists(self.ledger_path):
            self.load()

    # -----------------------------------------------------------------------
    # Job Ingestion & Deduplication
    # -----------------------------------------------------------------------

    def start_job(
        self,
        job_id: str,
        sop_id: str,
        tenant_id: str,
        content_sha256: str,
        uploaded_by: str,
        version: int = 1,
    ) -> JobRecord:
        """Initializes a new ingestion job in 'received' state.
        Detects duplicates (same SHA-256 + same tenant); if found, immediately marks duplicate.
        """
        with self._lock:
            # Check for existing processed record with same SHA-256 and tenant (Section 8)
            for existing in self._jobs.values():
                if (
                    existing.tenant_id == tenant_id
                    and existing.content_sha256 == content_sha256
                    and existing.current_state in {STATE_APPROVED, STATE_PUBLISHED, STATE_AWAITING_REVIEW}
                ):
                    dup_record = JobRecord(
                        job_id=job_id,
                        sop_id=sop_id,
                        tenant_id=tenant_id,
                        version=version,
                        content_sha256=content_sha256,
                        uploaded_by=uploaded_by,
                        current_state=STATE_DUPLICATE,
                    )
                    dup_record.history.append({
                        "from_state": STATE_RECEIVED,
                        "to_state": STATE_DUPLICATE,
                        "timestamp": _utc_now_iso(),
                        "actor": "orchestrator",
                        "reason": f"Duplicate document detected (matches {existing.sop_id} with SHA-256 {content_sha256[:12]}...)",
                    })
                    self._jobs[job_id] = dup_record
                    self._save_unlocked()
                    return dup_record

            job = JobRecord(
                job_id=job_id,
                sop_id=sop_id,
                tenant_id=tenant_id,
                version=version,
                content_sha256=content_sha256,
                uploaded_by=uploaded_by,
                current_state=STATE_RECEIVED,
            )
            job.history.append({
                "from_state": None,
                "to_state": STATE_RECEIVED,
                "timestamp": _utc_now_iso(),
                "actor": "orchestrator",
                "reason": "Ingestion job initialized after file intake checks.",
            })
            self._jobs[job_id] = job
            self._save_unlocked()
            return job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    # -----------------------------------------------------------------------
    # State Transition Engine (Section 8)
    # -----------------------------------------------------------------------

    def transition_state(
        self,
        job_id: str,
        next_state: str,
        actor: str = "orchestrator",
        reason: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Transitions job to next_state, strictly validating against ALLOWED_TRANSITIONS."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found in ledger.")

            current = job.current_state
            allowed = ALLOWED_TRANSITIONS.get(current, set())

            if next_state not in allowed:
                raise IllegalTransitionError(current_state=current, attempted_state=next_state)

            job.current_state = next_state
            job.updated_at = _utc_now_iso()
            job.history.append({
                "from_state": current,
                "to_state": next_state,
                "timestamp": job.updated_at,
                "actor": actor,
                "reason": reason,
                "details": details or {},
            })
            self._save_unlocked()
            return next_state

    # -----------------------------------------------------------------------
    # Terminal Secret Quarantine Protocol (Section 10)
    # -----------------------------------------------------------------------

    def trigger_quarantine(
        self,
        job_id: str,
        secrets_count: int,
        secret_types: List[str],
        actor: str = "A3_scanner",
    ) -> QuarantineIncident:
        """Immediately halts pipeline and transitions job to 'quarantined'.
        Emits INC-xxxxxx incident ticket, flags content as purged, and prevents AI calls.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found in ledger.")

            # Validate legal transition from current state to quarantined
            allowed = ALLOWED_TRANSITIONS.get(job.current_state, set())
            if STATE_QUARANTINED not in allowed:
                raise IllegalTransitionError(job.current_state, STATE_QUARANTINED)

            incident_id = generate_incident_id()
            incident = QuarantineIncident(
                incident_id=incident_id,
                sop_id=job.sop_id,
                job_id=job.job_id,
                content_sha256=job.content_sha256,
                secrets_count=secrets_count,
                secret_types=secret_types,
                purged=True,
            )

            job.current_state = STATE_QUARANTINED
            job.purged = True
            job.incident = asdict(incident)
            job.updated_at = _utc_now_iso()
            job.history.append({
                "from_state": STATE_SCANNING,
                "to_state": STATE_QUARANTINED,
                "timestamp": job.updated_at,
                "actor": actor,
                "reason": f"Terminal quarantine triggered: {secrets_count} credentials detected.",
                "details": {"incident_id": incident_id, "secret_types": secret_types},
            })

            self._save_unlocked()
            return incident

    # -----------------------------------------------------------------------
    # Review Task Coordination (Section 5.5 & 13)
    # -----------------------------------------------------------------------

    def create_review_task(
        self,
        job_id: str,
        confidentiality_score: int,
        confidentiality_level: str,
    ) -> ReviewTask:
        """Creates an RT-xxxxxx human review task when job reaches awaiting_review.
        Assigns to 'Security reviewer' (24h SLA) if score >= 60 or L2/L3, else 'Process owner' (48h SLA).
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found in ledger.")

            # Transition to awaiting_review if not already there
            if job.current_state != STATE_AWAITING_REVIEW:
                self.transition_state(
                    job_id,
                    STATE_AWAITING_REVIEW,
                    actor="A5_coordinator",
                    reason="Assessment completed; routing to human review.",
                )

            # Determine role and deadline per Section 5.5 & 11
            requires_security = (confidentiality_score >= 60) or (confidentiality_level in {"L2", "L3"})
            assigned_role = "Security reviewer" if requires_security else "Process owner"
            sla_hours = 24 if requires_security else 48

            now = datetime.datetime.now(datetime.timezone.utc)
            due_date = (now + datetime.timedelta(hours=sla_hours)).isoformat()

            task_id = generate_review_task_id()
            task = ReviewTask(
                task_id=task_id,
                sop_id=job.sop_id,
                job_id=job.job_id,
                version=job.version,
                content_sha256=job.content_sha256,
                assigned_role=assigned_role,
                due_date=due_date,
                uploaded_by=job.uploaded_by,
                status="pending",
            )

            job.review_task = asdict(task)
            job.updated_at = _utc_now_iso()
            self._save_unlocked()
            return task

    # -----------------------------------------------------------------------
    # Review Decision Recording & SoD Gate (Section 5.5 & 13)
    # -----------------------------------------------------------------------

    def record_review_decision(
        self,
        job_id: str,
        decision: str,  # "approve", "changes_requested", "reject"
        reviewer: str,
        actor_type: str = "human",
        notes: str = "",
        publication_gate_check: Optional[PublicationGateResult] = None,
        last_editor: Optional[str] = None,
    ) -> ReviewDecision:
        """Records a human review decision with strict Separation of Duties validation."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found in ledger.")

            if job.current_state != STATE_AWAITING_REVIEW:
                raise GovernanceError(
                    f"Cannot record review decision while job is in state '{job.current_state}'. Must be 'awaiting_review'.",
                    error_code="invalid_state",
                )

            # 1. Non-negotiable rule: only human actors can make review decisions (Section 10.1)
            if actor_type != "human":
                raise NotHumanActorError("Automated agent approval strictly prohibited. Must be actor_type='human'.")

            # 2. Separation of Duties enforcement (Section 13)
            sod_ok, sod_err = verify_separation_of_duties(
                uploaded_by=job.uploaded_by,
                reviewer=reviewer,
                last_editor=last_editor,
            )
            if not sod_ok:
                raise SeparationOfDutiesViolation(sod_err or "Separation of Duties check failed.")

            clean_decision = decision.strip().lower()

            # 3. Handle 'approve'
            if clean_decision == "approve":
                # Must verify all publication gates if provided
                if publication_gate_check and not publication_gate_check.passed:
                    raise GateFailureError(
                        "Approval rejected because publication gates failed",
                        publication_gate_check.failure_reasons,
                    )
                next_state = STATE_APPROVED
            elif clean_decision == "changes_requested":
                next_state = STATE_CHANGES_REQUESTED
            elif clean_decision in {"reject", "rejected"}:
                next_state = STATE_REJECTED
            else:
                raise ValueError(f"Unknown review decision '{decision}'. Must be 'approve', 'changes_requested', or 'reject'.")

            # Update review task if present
            if job.review_task:
                job.review_task["status"] = clean_decision
                job.review_task["reviewer"] = reviewer
                job.review_task["notes"] = notes
                job.review_task["completed_at"] = _utc_now_iso()

            rec = ReviewDecision(
                decision=clean_decision,
                reviewer=reviewer,
                actor_type="human",
                sop_id=job.sop_id,
                version=job.version,
                content_sha256=job.content_sha256,
                notes=notes,
            )
            job.approval_decision = asdict(rec)
            if publication_gate_check:
                job.gate_results = asdict(publication_gate_check)

            # Transition state
            self.transition_state(
                job_id,
                next_state,
                actor=reviewer,
                reason=f"Human review decision recorded: {clean_decision}. Notes: {notes}",
            )
            return rec

    # -----------------------------------------------------------------------
    # Publication & Stale Approval Verification (Section 5.6 & 9)
    # -----------------------------------------------------------------------

    def publish_approved_sop(
        self,
        job_id: str,
        current_content_sha256: str,
        current_version: int,
        publication_gate_check: PublicationGateResult,
        actor: str = "A6_hub",
    ) -> bool:
        """Publishes an approved SOP, strictly verifying version, hash integrity, and gates."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found in ledger.")

            # 1. State must be 'approved'
            if job.current_state != STATE_APPROVED:
                raise NotApprovedError(f"Job is in state '{job.current_state}', cannot publish. Must be 'approved'.")

            if not job.approval_decision:
                raise NotApprovedError("No recorded approval decision found for this job.")

            # 2. Version & content hash consistency check (Section 5.6)
            approved_hash = job.approval_decision.get("content_sha256")
            approved_ver = job.approval_decision.get("version")

            if approved_ver != current_version:
                raise StaleApprovalError(
                    f"Version mismatch: Approved version is v{approved_ver}, but current version is v{current_version}."
                )

            if approved_hash != current_content_sha256:
                raise StaleApprovalError(
                    "Content hash mismatch: Document content has been modified since human approval was recorded."
                )

            # 3. Re-verify all 6 publication gates at execution time (Section 5.6)
            if not publication_gate_check.passed:
                raise GateFailureError(
                    "Publish blocked: Publication gates failed at publish execution check",
                    publication_gate_check.failure_reasons,
                )

            job.gate_results = asdict(publication_gate_check)
            self.transition_state(
                job_id,
                STATE_PUBLISHED,
                actor=actor,
                reason="All publication gates verified and content hash matches approval stamp.",
            )
            return True

    # -----------------------------------------------------------------------
    # Lifecycle Management: Deactivate, Archive, Soft Delete, Restore (Section 5.6)
    # -----------------------------------------------------------------------

    def deactivate_sop(self, job_id: str, actor: str, role: str = "owner") -> bool:
        """Deactivates a published SOP. Role must be admin or owner."""
        if role.lower() not in {"admin", "owner"}:
            raise GovernanceError("Deactivation requires role 'admin' or 'owner'.", error_code="not_authorized")
        self.transition_state(job_id, STATE_DEACTIVATED, actor=actor, reason="Deactivated by authorized user.")
        return True

    def archive_sop(self, job_id: str, actor: str, role: str = "owner") -> bool:
        """Archives a published or deactivated SOP. Role must be admin or owner."""
        if role.lower() not in {"admin", "owner"}:
            raise GovernanceError("Archival requires role 'admin' or 'owner'.", error_code="not_authorized")
        self.transition_state(job_id, STATE_ARCHIVED, actor=actor, reason="Archived by authorized user.")
        return True

    def soft_delete_sop(self, job_id: str, actor: str, role: str = "owner") -> bool:
        """Soft-deletes an SOP. Role must be admin or owner."""
        if role.lower() not in {"admin", "owner"}:
            raise GovernanceError("Soft deletion requires role 'admin' or 'owner'.", error_code="not_authorized")
        self.transition_state(job_id, STATE_SOFT_DELETED, actor=actor, reason="Soft-deleted by authorized user.")
        return True

    def restore_sop(self, job_id: str, actor: str, role: str = "owner") -> bool:
        """Restores a soft-deleted SOP back to deactivated state."""
        if role.lower() not in {"admin", "owner"}:
            raise GovernanceError("Restoration requires role 'admin' or 'owner'.", error_code="not_authorized")
        self.transition_state(job_id, STATE_DEACTIVATED, actor=actor, reason="Restored from soft_deleted state.")
        return True

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def _save_unlocked(self):
        if not self.ledger_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.ledger_path)), exist_ok=True)
        tmp_path = f"{self.ledger_path}.tmp"
        data = {k: v.to_dict() for k, v in self._jobs.items()}
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, self.ledger_path)

    def save(self):
        with self._lock:
            self._save_unlocked()

    def load(self):
        with self._lock:
            if not self.ledger_path or not os.path.exists(self.ledger_path):
                return
            if os.path.getsize(self.ledger_path) == 0:
                self._jobs = {}
                return
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._jobs = {k: JobRecord.from_dict(v) for k, v in data.items()}


# Alias
GovernanceLedger = OrchestratorLedger

