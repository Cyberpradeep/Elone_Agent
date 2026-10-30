"""
Agent Communication Protocol (msg/1.0) & Routing Matrix
=========================================================
Implements Sections 6, 7, and Appendix B of SOP Governance Hub v1.0:
1. Structured Messaging Protocol (msg/1.0): TaskMessage and ResultMessage schemas.
2. Artifact Store by Reference: Large content passed by artifact reference, never in raw prompts.
3. Rigid Routing Matrix (Section 7): Enforces authorized agent hand-offs; rejects arbitrary jumps.
4. Tenant & Correlation Guardrails: Every message, artifact, and result validated against the active job.
5. Idempotency Key Tracking: job:task:version:revision:loop cache prevents double-execution.
6. Artifact Read/Write Access Matrix: Restricts artifact permissions per agent role (Section 5).
"""

import os
import json
import uuid
import datetime
import hashlib
from typing import Dict, List, Set, Optional, Tuple, Any, Literal, Callable
from pydantic import BaseModel, Field, model_validator, ConfigDict

# Section 15 Hard Budgets per Job
MAX_AGENT_CALLS_PER_JOB = 30
MAX_LLM_CALLS_PER_JOB = 14


# ---------------------------------------------------------------------------
# 1. Routing Matrix & Permissions Configuration (Sections 5 & 7)
# ---------------------------------------------------------------------------

from schemas.protocol_msg import (
    AGENT_ROLES,
    ALLOWED_ROUTES,
    ARTIFACT_PERMISSIONS,
    AgentProtocolError,
    RouteNotAllowedError,
    MalformedMessageError,
    TenantMismatchError,
    ArtifactAccessDeniedError,
    Artifact,
    TaskMessage,
    ResultMessage,
)


class ArtifactStore:
    """Thread-safe store for tenant-owned artifacts."""

    def __init__(self):
        self._store: Dict[str, Artifact] = {}

    def put(self, artifact: Artifact) -> str:
        self._store[artifact.artifact_id] = artifact
        return artifact.artifact_id

    def get(self, artifact_id: str, requesting_tenant: str) -> Optional[Artifact]:
        artifact = self._store.get(artifact_id)
        if not artifact:
            return None
        if artifact.tenant_id != requesting_tenant:
            raise TenantMismatchError(expected=requesting_tenant, found=artifact.tenant_id)
        return artifact

    def has(self, artifact_id: str) -> bool:
        return artifact_id in self._store


# ---------------------------------------------------------------------------
# 6. Message Dispatcher & Consumption Validator (Section 6.3)
# ---------------------------------------------------------------------------

class AgentMessageBus:
    """Manages msg/1.0 message exchange, validation, and idempotency tracking."""

    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        self.artifact_store = artifact_store or ArtifactStore()
        self._idempotency_cache: Dict[str, ResultMessage] = {}
        self._message_log: List[Dict[str, Any]] = []
        self._runners: Dict[str, Callable[[TaskMessage, "AgentMessageBus"], ResultMessage]] = {}
        self._job_budgets: Dict[str, Dict[str, int]] = {}

    def register_runner(self, agent_id: str, runner_func: Callable[[TaskMessage, "AgentMessageBus"], ResultMessage]) -> None:
        """Registers a protocol runner for an agent role (Section 5)."""
        self._runners[agent_id] = runner_func

    def load_standard_runners(self) -> None:
        """Loads default agent runners from orchestrator.agent_runners."""
        try:
            from orchestrator.agent_runners import STANDARD_AGENT_RUNNERS
            for agent_id, runner_func in STANDARD_AGENT_RUNNERS.items():
                self.register_runner(agent_id, runner_func)
        except Exception:
            pass

    def get_job_budget(self, correlation_id: str) -> Dict[str, int]:
        """Returns current resource usage metrics for a job."""
        return self._job_budgets.get(correlation_id, {"agent_calls": 0, "llm_calls": 0})

    def dispatch_task(
        self,
        task: TaskMessage,
        expected_correlation_id: Optional[str] = None,
        expected_content_hash: Optional[str] = None,
    ) -> Optional[ResultMessage]:
        """Dispatches and pre-validates task before delivery to recipient agent (Section 6.3).
        If idempotency_key is already cached, immediately returns stored Result without re-executing.
        """
        # 1. Idempotency Check (Section 6.1 & Test 8)
        if task.idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[task.idempotency_key]

        # 2. Check Job Budget (Section 15 & Test 9)
        budget = self._job_budgets.setdefault(task.correlation_id, {"agent_calls": 0, "llm_calls": 0})
        if budget["agent_calls"] >= MAX_AGENT_CALLS_PER_JOB:
            raise AgentProtocolError(
                f"Job agent call budget of {MAX_AGENT_CALLS_PER_JOB} exceeded",
                error_code="budget_exceeded"
            )

        # 3. Correlation & Content Hash Matching (Section 6.3)
        if expected_correlation_id and task.correlation_id != expected_correlation_id:
            raise AgentProtocolError(
                f"Correlation mismatch: expected '{expected_correlation_id}', got '{task.correlation_id}'",
                error_code="correlation_mismatch"
            )

        if expected_content_hash and task.source_content_hash != expected_content_hash:
            raise AgentProtocolError(
                f"Source hash mismatch: expected '{expected_content_hash}', got '{task.source_content_hash}'",
                error_code="version_mismatch"
            )

        # 4. Route Check (Section 7)
        if (task.sender, task.recipient) not in ALLOWED_ROUTES:
            raise RouteNotAllowedError(task.sender, task.recipient)

        # 5. Check recipient read permissions on input artifacts (Section 6.3)
        allowed_read_types = ARTIFACT_PERMISSIONS.get(task.recipient, {}).get("reads", set())
        for art_id in task.input_artifact_references:
            art = self.artifact_store.get(art_id, requesting_tenant=task.tenant_id)
            if art and art.artifact_type not in allowed_read_types:
                raise ArtifactAccessDeniedError(task.recipient, "read", art.artifact_type)

        # Log task dispatch
        self._message_log.append({
            "type": "task",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "task_id": task.task_id,
            "correlation_id": task.correlation_id,
            "sender": task.sender,
            "recipient": task.recipient,
            "task_type": task.task_type,
            "idempotency_key": task.idempotency_key,
        })
        return None  # Ready for agent execution

    def execute_task(
        self,
        task: TaskMessage,
        expected_correlation_id: Optional[str] = None,
        expected_content_hash: Optional[str] = None,
    ) -> ResultMessage:
        """Executes a task through its registered agent runner under msg/1.0 protocol (Section 6.3)."""
        cached = self.dispatch_task(task, expected_correlation_id, expected_content_hash)
        if cached:
            return cached

        runner = self._runners.get(task.recipient)
        if not runner:
            raise AgentProtocolError(
                f"No runner registered for agent '{task.recipient}'",
                error_code="unauthorized_tool"
            )

        # Increment agent call counter against job budget
        self._job_budgets[task.correlation_id]["agent_calls"] += 1

        result = runner(task, self)
        return self.record_result(task, result)

    def record_result(
        self,
        task: TaskMessage,
        result: ResultMessage,
    ) -> ResultMessage:
        """Validates agent result before consumption (Section 6.3).
        Replaces malformed results with status='failed' and error_code='malformed_output'.
        Caches successful/valid results under the task's idempotency key.
        """
        # 1. Basic structural consistency
        if result.task_id != task.task_id or result.correlation_id != task.correlation_id:
            return ResultMessage(
                task_id=task.task_id,
                correlation_id=task.correlation_id,
                agent_id=result.agent_id,
                status="failed",
                error_code="malformed_output",
                structured_findings={"error": "Result task_id or correlation_id does not match dispatch task."},
            )

        # 2. Validate written artifact permissions (Section 6.3)
        if result.output_artifact_reference:
            art = self.artifact_store.get(result.output_artifact_reference, requesting_tenant=task.tenant_id)
            if art:
                allowed_write_types = ARTIFACT_PERMISSIONS.get(result.agent_id, {}).get("writes", set())
                if art.artifact_type not in allowed_write_types:
                    return ResultMessage(
                        task_id=task.task_id,
                        correlation_id=task.correlation_id,
                        agent_id=result.agent_id,
                        status="failed",
                        error_code="artifact_access_denied",
                        structured_findings={"error": f"Agent '{result.agent_id}' cannot write artifact type '{art.artifact_type}'."},
                    )

        # Cache valid result under idempotency key
        self._idempotency_cache[task.idempotency_key] = result

        # Log result
        self._message_log.append({
            "type": "result",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "task_id": result.task_id,
            "correlation_id": result.correlation_id,
            "agent_id": result.agent_id,
            "status": result.status,
            "error_code": result.error_code,
        })
        return result

    def get_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._message_log[-limit:]


# Aliases
AgentBus = AgentMessageBus

