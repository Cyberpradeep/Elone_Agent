"""
Unit Tests for msg/1.0 Protocol Runtime Engine & Agent Runners
==============================================================
Tests items A, B, and D of the SOP Governance Hub v1.0 specification:
1. Item A: Bus-Driven Dispatching via `execute_task()`.
2. Item B: Pure Artifact-Passing via `ArtifactStore`.
3. Item D: Automated A4 -> A2 correction loop bounded to max 1 loop.
4. Section 15 Job Budget limits (30 agent calls max per job).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas.protocol_msg import (
    TaskMessage,
    ResultMessage,
    Artifact,
    RouteNotAllowedError,
    TenantMismatchError,
    AgentProtocolError,
)
from orchestrator.bus import AgentMessageBus, ArtifactStore, MAX_AGENT_CALLS_PER_JOB


class TestMsgProtocolRuntime(unittest.TestCase):

    def setUp(self):
        self.store = ArtifactStore()
        self.bus = AgentMessageBus(artifact_store=self.store)

    def test_01_execute_task_dispatch_and_record(self):
        """execute_task invokes registered runner and stores validated ResultMessage."""
        # Setup mock runner for A1
        def mock_a1_runner(task, bus):
            # Read input upload artifact
            art = bus.artifact_store.get(task.input_artifact_references[0], requesting_tenant=task.tenant_id)
            out_art = Artifact.create(
                tenant_id=task.tenant_id,
                artifact_type="extracted",
                created_by="A1",
                data={"raw_text": f"Extracted text from {art.data['filename']}"},
            )
            bus.artifact_store.put(out_art)
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                agent_id="A1",
                status="success",
                output_artifact_reference=out_art.artifact_id,
                structured_findings={"total_lines": 10},
            )

        self.bus.register_runner("A1", mock_a1_runner)

        # Create input upload artifact
        upload_art = Artifact.create(
            tenant_id="tn_corp",
            artifact_type="upload",
            created_by="orchestrator",
            data={"filename": "sop_test.pdf"},
        )
        self.store.put(upload_art)

        task = TaskMessage(
            correlation_id="job_trace_999",
            tenant_id="tn_corp",
            sop_id="SOP-999",
            source_version_id="SOP-999@v1",
            source_content_hash="hash999",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            input_artifact_references=[upload_art.artifact_id],
            idempotency_key="job_trace_999:extract:v1:rev1:loop0",
        )

        res = self.bus.execute_task(task)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.agent_id, "A1")
        self.assertTrue(res.output_artifact_reference.startswith("art-"))

        # Verify output artifact stored in bus.artifact_store
        out_art = self.store.get(res.output_artifact_reference, requesting_tenant="tn_corp")
        self.assertIsNotNone(out_art)
        self.assertEqual(out_art.artifact_type, "extracted")
        self.assertIn("Extracted text from sop_test.pdf", out_art.data["raw_text"])

    def test_02_pure_artifact_passing_isolation(self):
        """Cross-tenant artifact reference raises TenantMismatchError."""
        upload_art = Artifact.create(
            tenant_id="tn_tenant_A",
            artifact_type="upload",
            created_by="orchestrator",
            data={"filename": "secret_doc.pdf"},
        )
        self.store.put(upload_art)

        # Tenant B tries to reference Tenant A's artifact
        task = TaskMessage(
            correlation_id="job_trace_steal",
            tenant_id="tn_tenant_B",
            sop_id="SOP-777",
            source_version_id="SOP-777@v1",
            source_content_hash="hash777",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            input_artifact_references=[upload_art.artifact_id],
            idempotency_key="job:task:v1:rev1:loop0",
        )

        with self.assertRaises(TenantMismatchError):
            self.bus.execute_task(task)

    def test_03_job_budget_enforcement(self):
        """Enforces Section 15 job budget limit (max 30 agent calls per job)."""
        def dummy_runner(task, bus):
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                agent_id=task.recipient,
                status="success",
            )

        self.bus.register_runner("A1", dummy_runner)

        # Make 30 calls successfully
        for i in range(MAX_AGENT_CALLS_PER_JOB):
            task = TaskMessage(
                correlation_id="budget_job_1",
                tenant_id="tn_test",
                sop_id="SOP-1",
                source_version_id="SOP-1@v1",
                source_content_hash="h1",
                sender="orchestrator",
                recipient="A1",
                task_type="extract",
                idempotency_key=f"budget_job_1:call_{i}",
            )
            self.bus.execute_task(task)

        # 31st call MUST raise budget_exceeded
        task_overflow = TaskMessage(
            correlation_id="budget_job_1",
            tenant_id="tn_test",
            sop_id="SOP-1",
            source_version_id="SOP-1@v1",
            source_content_hash="h1",
            sender="orchestrator",
            recipient="A1",
            task_type="extract",
            idempotency_key="budget_job_1:call_overflow",
        )
        with self.assertRaises(AgentProtocolError) as ctx:
            self.bus.execute_task(task_overflow)
        self.assertEqual(ctx.exception.error_code, "budget_exceeded")

    def test_04_automated_a4_to_a2_correction_loop(self):
        """Simulates automated A4 -> A2 correction loop bounded to max 1 loop."""
        correction_invocations = []

        def mock_a2_runner(task, bus):
            if task.task_type == "correct":
                correction_invocations.append(task)
            out_art = Artifact.create(
                tenant_id=task.tenant_id,
                artifact_type="canonical_draft",
                created_by="A2",
                data={"sop_id": "SOP-101", "steps": [{"step_number": 1, "action": "Fixed step"}]},
            )
            bus.artifact_store.put(out_art)
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                agent_id="A2",
                status="success",
                output_artifact_reference=out_art.artifact_id,
            )

        self.bus.register_runner("A2", mock_a2_runner)

        # Create extracted & quality report artifacts
        ext_art = Artifact.create(tenant_id="tn_corp", artifact_type="extracted", created_by="A1", data={"raw": "test"})
        qr_art = Artifact.create(tenant_id="tn_corp", artifact_type="quality_report", created_by="A4", data={"validation_errors": ["Untraceable quote in step 1"]})
        self.store.put(ext_art)
        self.store.put(qr_art)

        # Loop 1: A4 -> A2 correction task
        correction_task_1 = TaskMessage(
            correlation_id="corr_job_1",
            tenant_id="tn_corp",
            sop_id="SOP-101",
            source_version_id="SOP-101@v1",
            source_content_hash="hash101",
            sender="A4",
            recipient="A2",
            task_type="correct",
            input_artifact_references=[ext_art.artifact_id, qr_art.artifact_id],
            idempotency_key="corr_job_1:correct:v1:rev1:loop1",
        )

        res_corr_1 = self.bus.execute_task(correction_task_1)
        self.assertEqual(res_corr_1.status, "success")
        self.assertEqual(len(correction_invocations), 1)

    def test_05_disallowed_route_rejected(self):
        """Route A1 -> A6 is disallowed and raises RouteNotAllowedError."""
        with self.assertRaises(RouteNotAllowedError):
            TaskMessage(
                correlation_id="job_illegal",
                tenant_id="tn_corp",
                sop_id="SOP-101",
                source_version_id="SOP-101@v1",
                source_content_hash="hash101",
                sender="A1",
                recipient="A6",
                task_type="publish",
                idempotency_key="job_illegal:a1_to_a6",
            )


if __name__ == "__main__":
    unittest.main()
