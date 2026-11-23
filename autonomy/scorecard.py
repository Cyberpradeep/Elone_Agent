"""Autonomy Scorecard & Qualification Tracking Engine (Module A9).

Enforces:
- 10-Run Qualification Gate: Requires 10 consecutive successful runs in Supervised
  mode before an SOP qualifies for Policy-Based autonomous execution.
- Automatic Demotion Trigger: Any single execution failure, verification failure,
  step timeout, or rollback resets consecutive successes to 0 and immediately
  demotes the SOP back to Supervised mode.
- Thread-safe tracking with double-checked locking.
"""

from datetime import datetime
import threading
from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field
from orchestrator.state_graph import ExecutionModeEnum


QUALIFICATION_THRESHOLD = 10


class AutonomyScorecardRecord(BaseModel):
    """Immutable status snapshot for an SOP's autonomy qualification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sop_id: str
    consecutive_successes: int = Field(default=0, ge=0)
    total_runs: int = Field(default=0, ge=0)
    successful_runs: int = Field(default=0, ge=0)
    failed_runs: int = Field(default=0, ge=0)
    is_qualified: bool = False
    last_demoted_at: Optional[datetime] = None
    last_demoted_reason: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class AutonomyScorecard:
    """Thread-safe persistent tracker for SOP autonomy qualification and demotion."""

    def __init__(self, qualification_threshold: int = QUALIFICATION_THRESHOLD):
        self.qualification_threshold = qualification_threshold
        self._records: Dict[str, AutonomyScorecardRecord] = {}
        self._lock = threading.Lock()

    def get_scorecard(self, sop_id: str) -> AutonomyScorecardRecord:
        """Fetch current scorecard record for an SOP, initializing if absent."""
        with self._lock:
            if sop_id not in self._records:
                self._records[sop_id] = AutonomyScorecardRecord(
                    sop_id=sop_id,
                    last_updated=datetime.utcnow(),
                )
            return self._records[sop_id]

    def is_qualified_for_policy_mode(self, sop_id: str) -> bool:
        """Return True if the SOP has completed at least 10 consecutive successful runs."""
        record = self.get_scorecard(sop_id)
        return record.is_qualified

    def record_run(
        self,
        sop_id: str,
        success: bool,
        mode: ExecutionModeEnum = ExecutionModeEnum.SUPERVISED,
        reason: Optional[str] = None,
    ) -> AutonomyScorecardRecord:
        """Record the outcome of an execution run, updating consecutive successes or triggering demotion."""
        with self._lock:
            curr = self._records.get(
                sop_id,
                AutonomyScorecardRecord(sop_id=sop_id, last_updated=datetime.utcnow()),
            )

            now = datetime.utcnow()
            total = curr.total_runs + 1

            if success:
                successes = curr.successful_runs + 1
                failed = curr.failed_runs
                # Shadow runs don't count toward real operational qualification
                if mode in (ExecutionModeEnum.SUPERVISED, ExecutionModeEnum.POLICY_BASED):
                    consecutive = curr.consecutive_successes + 1
                else:
                    consecutive = curr.consecutive_successes

                qualified = consecutive >= self.qualification_threshold
                demoted_at = curr.last_demoted_at
                demoted_reason = curr.last_demoted_reason
            else:
                # Failure trigger: Immediate automatic demotion
                successes = curr.successful_runs
                failed = curr.failed_runs + 1
                consecutive = 0
                qualified = False
                demoted_at = now
                demoted_reason = reason or "Execution or verification failure"

            updated = AutonomyScorecardRecord(
                sop_id=sop_id,
                consecutive_successes=consecutive,
                total_runs=total,
                successful_runs=successes,
                failed_runs=failed,
                is_qualified=qualified,
                last_demoted_at=demoted_at,
                last_demoted_reason=demoted_reason,
                last_updated=now,
            )
            self._records[sop_id] = updated
            return updated

    def demote(self, sop_id: str, reason: str = "Manual operator demotion") -> AutonomyScorecardRecord:
        """Explicitly demote an SOP, resetting consecutive successes and qualification."""
        with self._lock:
            curr = self._records.get(
                sop_id,
                AutonomyScorecardRecord(sop_id=sop_id, last_updated=datetime.utcnow()),
            )
            now = datetime.utcnow()
            updated = AutonomyScorecardRecord(
                sop_id=sop_id,
                consecutive_successes=0,
                total_runs=curr.total_runs,
                successful_runs=curr.successful_runs,
                failed_runs=curr.failed_runs,
                is_qualified=False,
                last_demoted_at=now,
                last_demoted_reason=reason,
                last_updated=now,
            )
            self._records[sop_id] = updated
            return updated

    def reset(self, sop_id: str) -> None:
        """Reset all scorecard metrics for an SOP."""
        with self._lock:
            if sop_id in self._records:
                del self._records[sop_id]
