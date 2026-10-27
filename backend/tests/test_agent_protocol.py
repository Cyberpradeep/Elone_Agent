"""
Unit Tests for Agent Communication Protocol (msg/1.0) & Routing Matrix
========================================================================
Tests Sections 5, 6, 7, and Appendix B of SOP Governance Hub v1.0:
1. Valid msg/1.0 task and result envelope creation.
2. Rigid routing matrix enforcement (Section 7).
3. Rejection of unapproved routes (e.g. A1 -> A6 raises route_not_allowed, Test #4).
4. Tenant isolation on artifacts (Test #2 & #3).
5. Passing content by artifact reference instead of raw prompt copying.
6. Role-based artifact read/write permissions (Section 5).
7. Idempotency key tracking returning stored result (Test #8).
8. Correlation ID and content hash verification before task consumption.
9. Malformed result detection and replacement with malformed_output (Test #5).
"""

import os
import sys
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.bus import (
    TaskMessage,
    ResultMessage,
    Artifact,
    ArtifactStore,
    AgentMessageBus,
    RouteNotAllowedError,
    TenantMismatchError,
    ArtifactAccessDeniedError,
    AgentProtocolError,
    ALLOWED_ROUTES,
)


class TestAgentProtocol(unittest.TestCase):

    def setUp(self):
        self.store = ArtifactStore()
        self.bus = AgentMessageBus(artifact_store=self.store)

    def test_01_valid_task_envelope_creation(self):
        """TaskMessage creates with default msg/1.0 schema version and valid route."""
        task = TaskMessage(
            correlation_id="job_trace_101",
            tenant_id="tn_northwind",
            sop_id="SOP-1042",
            source_version_id="SOP-1042@v1",
            source_content_hash="hash123",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            idempotency_key="job:task:1:0:0",
        )
        self.assertEqual(task.schema_version, "msg/1.0")
        self.assertTrue(task.task_id.startswith("tsk-"))
        self.assertEqual(task.sender, "orchestrator")
        self.assertEqual(task.recipient, "A1")

    def test_02_all_allowed_routes_pass(self):
        """Every route specified in Section 7 routing matrix must be accepted."""
        for sender, recipient in ALLOWED_ROUTES:
            task = TaskMessage(
                correlation_id="trace_test",
                tenant_id="tenant_a",
                sop_id="SOP-01",
                source_version_id="SOP-01@v1",
                source_content_hash="h1",
                sender=sender,
                recipient=recipient,
                task_type="test_op",
                idempotency_key=f"{sender}:{recipient}:1",
            )
            self.assertEqual(task.sender, sender)
            self.assertEqual(task.recipient, recipient)

    def test_03_disallowed_route_rejected_with_error(self):
        """Direct jump A1 -> A6 is disallowed and must raise RouteNotAllowedError (Test #4)."""
        with self.assertRaises(RouteNotAllowedError) as exc:
            TaskMessage(
                correlation_id="trace_illegal",
                tenant_id="tenant_a",
                sop_id="SOP-01",
                source_version_id="SOP-01@v1",
                source_content_hash="h1",
                sender="A1",
                recipient="A6",  # Disallowed route!
                task_type="publish",
                idempotency_key="illegal_route_key",
            )
        self.assertEqual(exc.exception.error_code, "route_not_allowed")
        self.assertEqual(exc.exception.sender, "A1")
        self.assertEqual(exc.exception.recipient, "A6")

    def test_04_circular_or_arbitrary_agent_chat_blocked(self):
        """Free agent-to-agent talk (e.g. A3 -> A1) is forbidden."""
        with self.assertRaises(RouteNotAllowedError) as exc:
            TaskMessage(
                correlation_id="trace_chat",
                tenant_id="tenant_a",
                sop_id="SOP-01",
                source_version_id="SOP-01@v1",
                source_content_hash="h1",
                sender="A3",
                recipient="A1",
                task_type="chat",
                idempotency_key="k1",
            )
        self.assertEqual(exc.exception.error_code, "route_not_allowed")

    def test_05_artifact_by_reference_storage(self):
        """Artifacts are saved and referenced by artifact_id without inlining large text."""
        art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="extracted",
            created_by="A1",
            data={"lines": ["Line 1", "Line 2", "Line 3"]},
        )
        self.assertTrue(art.artifact_id.startswith("art-"))
        self.assertEqual(len(art.content_sha256), 64)  # Valid SHA-256

        self.store.put(art)
        retrieved = self.store.get(art.artifact_id, requesting_tenant="tn_northwind")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.artifact_type, "extracted")

    def test_06_tenant_isolation_on_artifacts(self):
        """Querying an artifact from another tenant raises TenantMismatchError (Test #2 & #3)."""
        art = Artifact.create(
            tenant_id="tenant_alpha",
            artifact_type="extracted",
            created_by="A1",
            data="Sensitive Alpha content",
        )
        self.store.put(art)

        # Tenant Beta tries to fetch Tenant Alpha's artifact
        with self.assertRaises(TenantMismatchError) as exc:
            self.store.get(art.artifact_id, requesting_tenant="tenant_beta")
        self.assertEqual(exc.exception.error_code, "tenant_mismatch")

    def test_07_artifact_read_permission_enforcement(self):
        """Agent A1 cannot read quality_report (only 'upload' is allowed per Section 5)."""
        art = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="quality_report",
            created_by="A4",
            data={"quality_score": 95},
        )
        self.store.put(art)

        # Dispatch task to A1 referencing quality_report as input
        task = TaskMessage(
            correlation_id="corr_perm",
            tenant_id="tn_northwind",
            sop_id="SOP-01",
            source_version_id="SOP-01@v1",
            source_content_hash="hash1",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            input_artifact_references=[art.artifact_id],
            idempotency_key="perm_key_1",
        )
        with self.assertRaises(ArtifactAccessDeniedError) as exc:
            self.bus.dispatch_task(task)
        self.assertEqual(exc.exception.error_code, "artifact_access_denied")

    def test_08_artifact_write_permission_enforcement(self):
        """Agent A1 cannot write artifact type 'cleaned' (only A2 may write cleaned)."""
        art_bad = Artifact.create(
            tenant_id="tn_northwind",
            artifact_type="cleaned",  # A1 is not allowed to write cleaned
            created_by="A1",
            data="Cleaned text",
        )
        self.store.put(art_bad)

        task = TaskMessage(
            correlation_id="corr_write",
            tenant_id="tn_northwind",
            sop_id="SOP-01",
            source_version_id="SOP-01@v1",
            source_content_hash="hash1",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            idempotency_key="write_key_1",
        )
        self.bus.dispatch_task(task)

        # Agent A1 attempts to return an artifact of type 'cleaned'
        result = ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A1",
            status="success",
            output_artifact_reference=art_bad.artifact_id,
        )
        consumed = self.bus.record_result(task, result)
        self.assertEqual(consumed.status, "failed")
        self.assertEqual(consumed.error_code, "artifact_access_denied")

    def test_09_idempotency_key_returns_cached_result(self):
        """Repeating a task with same idempotency_key returns cached result without re-executing (Test #8)."""
        task = TaskMessage(
            correlation_id="corr_idem",
            tenant_id="tn_northwind",
            sop_id="SOP-10",
            source_version_id="SOP-10@v1",
            source_content_hash="hash10",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            idempotency_key="job1:task1:v1:r0:l0",
        )
        # First dispatch -> needs execution
        cached = self.bus.dispatch_task(task)
        self.assertIsNone(cached)

        # Record result
        res = ResultMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            agent_id="A1",
            status="success",
            structured_findings={"lines_extracted": 42},
        )
        self.bus.record_result(task, res)

        # Second dispatch with identical idempotency_key
        cached2 = self.bus.dispatch_task(task)
        self.assertIsNotNone(cached2)
        self.assertEqual(cached2.status, "success")
        self.assertEqual(cached2.structured_findings["lines_extracted"], 42)

    def test_10_correlation_id_mismatch_rejected(self):
        """Task with mismatched correlation ID is rejected (correlation_mismatch)."""
        task = TaskMessage(
            correlation_id="wrong_corr_id",
            tenant_id="tn_northwind",
            sop_id="SOP-10",
            source_version_id="SOP-10@v1",
            source_content_hash="h1",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            idempotency_key="key_mismatch",
        )
        with self.assertRaises(AgentProtocolError) as exc:
            self.bus.dispatch_task(task, expected_correlation_id="active_job_corr_123")
        self.assertEqual(exc.exception.error_code, "correlation_mismatch")

    def test_11_malformed_result_replaced(self):
        """Result with mismatched task_id is rejected and replaced with malformed_output (Test #5)."""
        task = TaskMessage(
            correlation_id="corr_malform",
            tenant_id="tn_northwind",
            sop_id="SOP-10",
            source_version_id="SOP-10@v1",
            source_content_hash="h1",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            idempotency_key="key_malform",
        )
        self.bus.dispatch_task(task)

        # Hostile or malformed result with fake task_id
        bad_result = ResultMessage(
            task_id="forged_task_id_999",
            correlation_id=task.correlation_id,
            agent_id="A1",
            status="success",
        )
        consumed = self.bus.record_result(task, bad_result)
        self.assertEqual(consumed.status, "failed")
        self.assertEqual(consumed.error_code, "malformed_output")


if __name__ == "__main__":
    unittest.main(verbosity=2)

