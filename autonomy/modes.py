"""Operational Mode Router & Autonomy Gating Controller (Module A9).

Controls execution mode routing across:
- SHADOW: Simulation mode (0 mutations permitted).
- SUPERVISED: Human sign-off required for Level 3 and Level 4 mutations.
- POLICY_BASED: Autonomous execution for qualified SOPs (requires >=10 consecutive successes).
"""

from typing import Optional, Tuple
from orchestrator.state_graph import ExecutionModeEnum
from autonomy.scorecard import AutonomyScorecard, QUALIFICATION_THRESHOLD


class UnqualifiedAutonomyError(Exception):
    """Raised when Policy-Based mode is requested for an unqualified SOP in strict mode."""
    pass


class ModeRouter:
    """Validates and enforces execution mode transitions based on autonomy qualification."""

    def __init__(
        self,
        scorecard: Optional[AutonomyScorecard] = None,
        strict_enforcement: bool = False,
    ):
        self.scorecard = scorecard or AutonomyScorecard()
        self.strict_enforcement = strict_enforcement

    def resolve_mode(
        self,
        sop_id: str,
        requested_mode: ExecutionModeEnum,
    ) -> Tuple[ExecutionModeEnum, str]:
        """Resolve requested operational mode against SOP qualification scorecard."""
        # 1. SHADOW mode is always permitted
        if requested_mode == ExecutionModeEnum.SHADOW:
            return ExecutionModeEnum.SHADOW, "Shadow mode active: all actions logged, zero mutations executed."

        # 2. SUPERVISED mode is always permitted
        if requested_mode == ExecutionModeEnum.SUPERVISED:
            return (
                ExecutionModeEnum.SUPERVISED,
                "Supervised mode active: operator approval required for Level 3 & 4 mutations.",
            )

        # 3. POLICY_BASED mode requires autonomy qualification gate
        if requested_mode == ExecutionModeEnum.POLICY_BASED:
            record = self.scorecard.get_scorecard(sop_id)
            if record.is_qualified:
                return (
                    ExecutionModeEnum.POLICY_BASED,
                    f"Policy-based autonomy authorized for SOP '{sop_id}' "
                    f"({record.consecutive_successes} consecutive successful runs).",
                )

            # Not qualified: handle strict enforcement or safe fallback
            msg = (
                f"SOP '{sop_id}' is unqualified for Policy-Based mode "
                f"({record.consecutive_successes}/{self.scorecard.qualification_threshold} required successes)."
            )
            if self.strict_enforcement:
                raise UnqualifiedAutonomyError(f"{msg} Strict mode rejected execution.")

            # Safe default fallback to SUPERVISED mode
            return ExecutionModeEnum.SUPERVISED, f"{msg} Falling back safely to Supervised mode."

        return ExecutionModeEnum.SUPERVISED, f"Unrecognized mode '{requested_mode}'. Defaulting to Supervised."
