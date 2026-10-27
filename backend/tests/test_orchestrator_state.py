"""
Comprehensive Unit Tests for 14-State Orchestrator Lifecycle & Gatekeeper
========================================================================
Tests all capabilities defined in Sections 8, 9, 10, and 13 of SOP Governance Hub v1.0:
1. Legal state progression through full lifecycle.
2. Illegal transition rejection (Appendix B error: illegal_transition).
3. Terminal state isolation (quarantined, duplicate, rejected, etc.).
4. Secret quarantine protocol & incident generation (INC-xxxxxx).
5. Duplicate detection by SHA-256 and tenant.
6. Review task creation (RT-xxxxxx), role routing & SLA calculation.
7. Separation of Duties (SoD) enforcement (uploader != reviewer).
8. Non-negotiable human-only approval check (not_human).
9. The 6 Publication Gates evaluation.
10. Stale approval & content modification detection.
11. SOP lifecycle management (deactivate, archive, soft_delete, restore).
12. Ledger persistence (atomic save and reload).
"""

import os
import sys
import tempfile
import datetime
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.ledger import (
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
    OrchestratorLedger,
    IllegalTransitionError,
    SeparationOfDutiesViolation,
    NotHumanActorError,
    GateFailureError,
    StaleApprovalError,
    NotApprovedError,
    GovernanceError,
    verify_separation_of_duties,
    evaluate_publication_gates,
    generate_incident_id,
    generate_review_task_id,
    ReviewTask,
)


class TestOrchestratorState(unittest.TestCase):

    def test_01_id_generators(self):
        """Verify incident and review task ID patterns."""
        inc_id = generate_incident_id()
        self.assertTrue(inc_id.startswith("INC-"))
        self.assertEqual(len(inc_id), 10)  # INC- + 6 hex chars

        task_id = generate_review_task_id()
        self.assertTrue(task_id.startswith("RT-"))
        self.assertEqual(len(task_id), 9)  # RT- (3) + 6 hex chars = 9

    def test_02_separation_of_duties(self):
        """Verify Separation of Duties rules (Section 13)."""
        # Valid independent reviewer
        ok, err = verify_separation_of_duties(uploaded_by="alice@corp.com", reviewer="bob@corp.com")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Uploader cannot approve own document
        ok, err = verify_separation_of_duties(uploaded_by="alice@corp.com", reviewer="alice@corp.com")
        self.assertFalse(ok)
        self.assertIn("Uploader 'alice@corp.com' cannot approve", err)

        # Case-insensitive check
        ok, err = verify_separation_of_duties(uploaded_by="Alice@corp.com", reviewer="ALICE@corp.com")
        self.assertFalse(ok)
        self.assertIn("cannot approve", err)

        # Empty reviewer rejected
        ok, err = verify_separation_of_duties(uploaded_by="alice@corp.com", reviewer="")
        self.assertFalse(ok)
        self.assertIn("Reviewer identity is required", err)

        # Last editor cannot approve own revisions
        ok, err = verify_separation_of_duties(
            uploaded_by="alice@corp.com", reviewer="carol@corp.com", last_editor="carol@corp.com"
        )
        self.assertFalse(ok)
        self.assertIn("Last editor 'carol@corp.com' cannot approve", err)

    def test_03_publication_gates_evaluation(self):
        """Verify the 6 publication gates checklist (Section 9.1)."""
        # All gates passing
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=88.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
            rule_ai_conflict=False,
        )
        self.assertTrue(res.passed)
        self.assertEqual(len(res.failure_reasons), 0)
        self.assertEqual(len(res.gates), 6)

        # Gate 1 failure: secrets detected
        res = evaluate_publication_gates(
            secrets_count=1,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=88.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("Gate 1 Failed" in r for r in res.failure_reasons))

        # Gate 2 failure: schema errors
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=False,
            schema_errors_count=2,
            traceability_pct=95.0,
            completeness_pct=88.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("Gate 2 Failed" in r for r in res.failure_reasons))

        # Gate 3 failure: traceability < 90%
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=89.5,
            completeness_pct=88.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("Gate 3 Failed" in r for r in res.failure_reasons))

        # Gate 4 failure: completeness < 80%
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=79.9,
            open_blocking_issues_count=0,
            classification_confirmed=True,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("Gate 4 Failed" in r for r in res.failure_reasons))

        # Gate 5 failure: open blocking issues
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=88.0,
            open_blocking_issues_count=1,
            classification_confirmed=True,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("Gate 5 Failed" in r for r in res.failure_reasons))

        # Gate 5 failure: rule vs AI conflict
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=88.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
            rule_ai_conflict=True,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("conflict" in r.lower() for r in res.failure_reasons))

        # Gate 6 failure: unconfirmed classification
        res = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=88.0,
            open_blocking_issues_count=0,
            classification_confirmed=False,
        )
        self.assertFalse(res.passed)
        self.assertTrue(any("Gate 6 Failed" in r for r in res.failure_reasons))

    def test_04_full_legal_orchestrator_lifecycle(self):
        """Verify full end-to-end legal state flow."""
        ledger = OrchestratorLedger()
        job = ledger.start_job(
            job_id="job_001",
            sop_id="SOP-1001",
            tenant_id="tenant_alpha",
            content_sha256="abc123hash",
            uploaded_by="author@example.com",
        )
        self.assertEqual(job.current_state, STATE_RECEIVED)

        # Transition extracting -> scanning -> structuring -> assessing
        ledger.transition_state("job_001", STATE_EXTRACTING)
        ledger.transition_state("job_001", STATE_SCANNING)
        ledger.transition_state("job_001", STATE_STRUCTURING)
        ledger.transition_state("job_001", STATE_ASSESSING)

        # Create review task (moves to awaiting_review)
        task = ledger.create_review_task("job_001", confidentiality_score=40, confidentiality_level="L1")
        self.assertEqual(task.assigned_role, "Process owner")
        self.assertEqual(job.current_state, STATE_AWAITING_REVIEW)

        # Human approval with passing gates
        gates = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=92.0,
            completeness_pct=85.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
        )
        decision = ledger.record_review_decision(
            job_id="job_001",
            decision="approve",
            reviewer="approver@example.com",
            actor_type="human",
            publication_gate_check=gates,
        )
        self.assertEqual(decision.decision, "approve")
        self.assertEqual(job.current_state, STATE_APPROVED)

        # Publish
        published = ledger.publish_approved_sop(
            job_id="job_001",
            current_content_sha256="abc123hash",
            current_version=1,
            publication_gate_check=gates,
        )
        self.assertTrue(published)
        self.assertEqual(job.current_state, STATE_PUBLISHED)

        # Lifecycle: deactivate -> archive -> soft_delete -> restore (deactivated)
        ledger.deactivate_sop("job_001", actor="admin@example.com", role="admin")
        self.assertEqual(job.current_state, STATE_DEACTIVATED)

        ledger.archive_sop("job_001", actor="admin@example.com", role="owner")
        self.assertEqual(job.current_state, STATE_ARCHIVED)

        ledger.soft_delete_sop("job_001", actor="admin@example.com", role="owner")
        self.assertEqual(job.current_state, STATE_SOFT_DELETED)

        ledger.restore_sop("job_001", actor="admin@example.com", role="admin")
        self.assertEqual(job.current_state, STATE_DEACTIVATED)

    def test_05_illegal_transitions_rejected(self):
        """Verify that illegal transitions raise IllegalTransitionError with code 'illegal_transition'."""
        ledger = OrchestratorLedger()
        ledger.start_job(
            job_id="job_002",
            sop_id="SOP-1002",
            tenant_id="tenant_alpha",
            content_sha256="hash2",
            uploaded_by="user@example.com",
        )

        # From received, jumping to published is illegal
        with self.assertRaises(IllegalTransitionError) as exc:
            ledger.transition_state("job_002", STATE_PUBLISHED)
        self.assertEqual(exc.exception.error_code, "illegal_transition")

        # From received to extracting is valid
        ledger.transition_state("job_002", STATE_EXTRACTING)

        # From extracting, jumping directly to approved is illegal
        with self.assertRaises(IllegalTransitionError) as exc:
            ledger.transition_state("job_002", STATE_APPROVED)
        self.assertEqual(exc.exception.error_code, "illegal_transition")

    def test_06_secret_quarantine_protocol(self):
        """Verify terminal quarantine: incident creation, purged flag, no further transitions allowed."""
        ledger = OrchestratorLedger()
        ledger.start_job(
            job_id="job_sec",
            sop_id="SOP-SEC",
            tenant_id="tenant_alpha",
            content_sha256="sechash",
            uploaded_by="user@example.com",
        )
        ledger.transition_state("job_sec", STATE_EXTRACTING)
        ledger.transition_state("job_sec", STATE_SCANNING)

        # Live secret found during scanning -> quarantine!
        incident = ledger.trigger_quarantine(
            job_id="job_sec",
            secrets_count=2,
            secret_types=["api_key", "password"],
        )
        self.assertTrue(incident.incident_id.startswith("INC-"))
        self.assertTrue(incident.purged)
        self.assertEqual(incident.secrets_count, 2)

        job = ledger.get_job("job_sec")
        self.assertEqual(job.current_state, STATE_QUARANTINED)
        self.assertTrue(job.purged)
        self.assertEqual(job.incident["incident_id"], incident.incident_id)

        # Terminal state: cannot transition out
        with self.assertRaises(IllegalTransitionError) as exc:
            ledger.transition_state("job_sec", STATE_STRUCTURING)
        self.assertEqual(exc.exception.error_code, "illegal_transition")

    def test_07_duplicate_detection(self):
        """Verify duplicate SHA-256 detection halts at terminal state 'duplicate'."""
        ledger = OrchestratorLedger()
        # First job approved
        j1 = ledger.start_job("job_dup_1", "SOP-D1", "tenant_a", "same_hash", "uploader_1")
        ledger.transition_state("job_dup_1", STATE_EXTRACTING)
        ledger.transition_state("job_dup_1", STATE_SCANNING)
        ledger.transition_state("job_dup_1", STATE_STRUCTURING)
        ledger.transition_state("job_dup_1", STATE_ASSESSING)
        ledger.create_review_task("job_dup_1", 30, "L1")
        ledger.record_review_decision("job_dup_1", "approve", "reviewer_1")

        # Second job with same SHA-256 and same tenant
        j2 = ledger.start_job("job_dup_2", "SOP-D2", "tenant_a", "same_hash", "uploader_2")
        self.assertEqual(j2.current_state, STATE_DUPLICATE)
        self.assertIn("Duplicate document detected", j2.history[-1]["reason"])

    def test_08_review_task_routing_and_sla(self):
        """Verify review task routing based on sensitivity score >= 60 or L2/L3."""
        ledger = OrchestratorLedger()

        # Score 40 (L1): Process Owner, 48h SLA
        j1 = ledger.start_job("j_l1", "SOP-L1", "t1", "hash_l1", "u1")
        ledger.transition_state("j_l1", STATE_EXTRACTING)
        ledger.transition_state("j_l1", STATE_SCANNING)
        ledger.transition_state("j_l1", STATE_STRUCTURING)
        ledger.transition_state("j_l1", STATE_ASSESSING)
        t1 = ledger.create_review_task("j_l1", confidentiality_score=40, confidentiality_level="L1")
        self.assertEqual(t1.assigned_role, "Process owner")
        due1 = datetime.datetime.fromisoformat(t1.due_date)
        created1 = datetime.datetime.fromisoformat(t1.created_at)
        diff_hours = (due1 - created1).total_seconds() / 3600
        self.assertAlmostEqual(diff_hours, 48, delta=0.1)

        # Score 65 (L2): Security Reviewer, 24h SLA
        j2 = ledger.start_job("j_l2", "SOP-L2", "t1", "hash_l2", "u1")
        ledger.transition_state("j_l2", STATE_EXTRACTING)
        ledger.transition_state("j_l2", STATE_SCANNING)
        ledger.transition_state("j_l2", STATE_STRUCTURING)
        ledger.transition_state("j_l2", STATE_ASSESSING)
        t2 = ledger.create_review_task("j_l2", confidentiality_score=65, confidentiality_level="L2")
        self.assertEqual(t2.assigned_role, "Security reviewer")
        due2 = datetime.datetime.fromisoformat(t2.due_date)
        created2 = datetime.datetime.fromisoformat(t2.created_at)
        diff_hours = (due2 - created2).total_seconds() / 3600
        self.assertAlmostEqual(diff_hours, 24, delta=0.1)

    def test_09_review_task_overdue_check(self):
        """Verify overdue detection on review tasks."""
        now = datetime.datetime.now(datetime.timezone.utc)
        task = ReviewTask(
            task_id="RT-TEST01",
            sop_id="SOP-01",
            job_id="job_01",
            version=1,
            content_sha256="abc",
            assigned_role="Process owner",
            due_date=(now - datetime.timedelta(hours=1)).isoformat(),  # Due 1 hour ago
            uploaded_by="uploader",
            status="pending",
        )
        self.assertTrue(task.is_overdue())

        # If completed, not overdue
        task.status = "approved"
        self.assertFalse(task.is_overdue())

    def test_10_sod_violation_in_record_decision(self):
        """Verify that uploader attempting to approve raises SeparationOfDutiesViolation."""
        ledger = OrchestratorLedger()
        ledger.start_job("job_sod", "SOP-SOD", "t1", "hash_sod", "sarah@company.com")
        ledger.transition_state("job_sod", STATE_EXTRACTING)
        ledger.transition_state("job_sod", STATE_SCANNING)
        ledger.transition_state("job_sod", STATE_STRUCTURING)
        ledger.transition_state("job_sod", STATE_ASSESSING)
        ledger.create_review_task("job_sod", 20, "L0")

        # Sarah attempts to approve her own document
        with self.assertRaises(SeparationOfDutiesViolation) as exc:
            ledger.record_review_decision(
                job_id="job_sod",
                decision="approve",
                reviewer="sarah@company.com",
                actor_type="human",
            )
        self.assertEqual(exc.exception.error_code, "separation_of_duties")

    def test_11_non_human_actor_approval_rejected(self):
        """Verify that automated AI cannot approve (must be actor_type='human')."""
        ledger = OrchestratorLedger()
        ledger.start_job("job_bot", "SOP-BOT", "t1", "hash_bot", "sarah@company.com")
        ledger.transition_state("job_bot", STATE_EXTRACTING)
        ledger.transition_state("job_bot", STATE_SCANNING)
        ledger.transition_state("job_bot", STATE_STRUCTURING)
        ledger.transition_state("job_bot", STATE_ASSESSING)
        ledger.create_review_task("job_bot", 20, "L0")

        # Bot attempts to approve
        with self.assertRaises(NotHumanActorError) as exc:
            ledger.record_review_decision(
                job_id="job_bot",
                decision="approve",
                reviewer="agent_a5_autonomous",
                actor_type="agent",
            )
        self.assertEqual(exc.exception.error_code, "not_human")

    def test_12_changes_requested_and_correction_flow(self):
        """Verify changes_requested routes to structuring and back."""
        ledger = OrchestratorLedger()
        ledger.start_job("job_cr", "SOP-CR", "t1", "hash_cr", "sarah@company.com")
        ledger.transition_state("job_cr", STATE_EXTRACTING)
        ledger.transition_state("job_cr", STATE_SCANNING)
        ledger.transition_state("job_cr", STATE_STRUCTURING)
        ledger.transition_state("job_cr", STATE_ASSESSING)
        ledger.create_review_task("job_cr", 20, "L0")

        # Human requests changes
        ledger.record_review_decision(
            job_id="job_cr",
            decision="changes_requested",
            reviewer="reviewer@company.com",
            notes="Please clarify step 4 safety equipment.",
        )
        job = ledger.get_job("job_cr")
        self.assertEqual(job.current_state, STATE_CHANGES_REQUESTED)

        # From changes_requested, agent A2 re-structures
        ledger.transition_state("job_cr", STATE_STRUCTURING)
        self.assertEqual(job.current_state, STATE_STRUCTURING)

    def test_13_stale_approval_protection(self):
        """Verify that publishing is blocked if content hash or version has changed since approval."""
        ledger = OrchestratorLedger()
        ledger.start_job("job_stale", "SOP-STALE", "t1", "original_hash", "uploader@company.com")
        ledger.transition_state("job_stale", STATE_EXTRACTING)
        ledger.transition_state("job_stale", STATE_SCANNING)
        ledger.transition_state("job_stale", STATE_STRUCTURING)
        ledger.transition_state("job_stale", STATE_ASSESSING)
        ledger.create_review_task("job_stale", 20, "L0")

        gates = evaluate_publication_gates(
            secrets_count=0,
            is_quarantined=False,
            schema_valid=True,
            schema_errors_count=0,
            traceability_pct=95.0,
            completeness_pct=90.0,
            open_blocking_issues_count=0,
            classification_confirmed=True,
        )
        ledger.record_review_decision("job_stale", "approve", "reviewer@company.com", publication_gate_check=gates)

        # 1. Content hash changed (e.g. tampering or unauthorized edit)
        with self.assertRaises(StaleApprovalError) as exc:
            ledger.publish_approved_sop(
                job_id="job_stale",
                current_content_sha256="modified_hash_tampered",
                current_version=1,
                publication_gate_check=gates,
            )
        self.assertEqual(exc.exception.error_code, "stale_approval")

        # 2. Version mismatch
        with self.assertRaises(StaleApprovalError) as exc:
            ledger.publish_approved_sop(
                job_id="job_stale",
                current_content_sha256="original_hash",
                current_version=2,  # approved was version 1
                publication_gate_check=gates,
            )
        self.assertEqual(exc.exception.error_code, "stale_approval")

    def test_14_unauthorized_lifecycle_roles_rejected(self):
        """Verify that deactivation/archival/deletion requires role 'admin' or 'owner'."""
        ledger = OrchestratorLedger()
        ledger.start_job("job_auth", "SOP-AUTH", "t1", "hash_auth", "u@co.com")
        ledger.transition_state("job_auth", STATE_EXTRACTING)
        ledger.transition_state("job_auth", STATE_SCANNING)
        ledger.transition_state("job_auth", STATE_STRUCTURING)
        ledger.transition_state("job_auth", STATE_ASSESSING)
        ledger.create_review_task("job_auth", 10, "L0")
        gates = evaluate_publication_gates(0, False, True, 0, 95.0, 90.0, 0, True)
        ledger.record_review_decision("job_auth", "approve", "rev@co.com", publication_gate_check=gates)
        ledger.publish_approved_sop("job_auth", "hash_auth", 1, gates)

        # Viewer or guest role rejected
        with self.assertRaises(GovernanceError) as exc:
            ledger.deactivate_sop("job_auth", actor="guest@co.com", role="viewer")
        self.assertEqual(exc.exception.error_code, "not_authorized")

    def test_15_ledger_persistence(self):
        """Verify that OrchestratorLedger correctly serializes and deserializes state."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            ledger_file = tf.name

        try:
            # Create and mutate ledger
            l1 = OrchestratorLedger(ledger_path=ledger_file)
            l1.start_job("job_persist", "SOP-P1", "tenant_x", "persisthash", "up@co.com")
            l1.transition_state("job_persist", STATE_EXTRACTING)
            l1.transition_state("job_persist", STATE_SCANNING)
            l1.transition_state("job_persist", STATE_STRUCTURING)
            l1.transition_state("job_persist", STATE_ASSESSING)
            l1.create_review_task("job_persist", 55, "L2")

            # Reload in fresh ledger instance
            l2 = OrchestratorLedger(ledger_path=ledger_file)
            job2 = l2.get_job("job_persist")
            self.assertIsNotNone(job2)
            self.assertEqual(job2.current_state, STATE_AWAITING_REVIEW)
            self.assertEqual(job2.review_task["assigned_role"], "Security reviewer")
            self.assertEqual(len(job2.history), 6)
        finally:
            if os.path.exists(ledger_file):
                os.remove(ledger_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
