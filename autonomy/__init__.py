"""Autonomy Subsystem & Scorecard Engine (Module A9).

Provides:
- AutonomyScorecard: Consecutive success tracking and automatic failure demotion.
- ModeRouter: Routing and gating for Shadow, Supervised, and Policy-Based modes.
- QUALIFICATION_THRESHOLD: 10-run qualification requirement.
"""

from autonomy.scorecard import (
    AutonomyScorecard,
    AutonomyScorecardRecord,
    QUALIFICATION_THRESHOLD,
)
from autonomy.modes import (
    ModeRouter,
    UnqualifiedAutonomyError,
)

__all__ = [
    "AutonomyScorecard",
    "AutonomyScorecardRecord",
    "QUALIFICATION_THRESHOLD",
    "ModeRouter",
    "UnqualifiedAutonomyError",
]
