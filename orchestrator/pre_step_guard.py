"""Pre-Mutation Hub Status Re-Check Guard.

Mandated by Security Rule 5 (Page 7) & Edge Case 4:
Immediately before dispatching each state-changing step, the orchestrator queries
the Hub to verify that the active SOP is still PUBLISHED and its canonical SHA-256
hash matches the original plan binding.
"""

from typing import Any, Dict, Optional
from hub_client.mock_hub import MockHubService


class PreStepGuardResult:
    """Outcome of pre-mutation Hub re-check."""

    def __init__(self, passed: bool, reason: str):
        self.passed = passed
        self.reason = reason


def verify_pre_step_guard(
    sop_id: str,
    expected_canonical_hash: str,
    hub_service: Optional[Any] = None,
) -> PreStepGuardResult:
    """Authoritative pre-step guard check against Hub before any mutation step.

    Fails closed if:
    1. Hub is unreachable (ConnectionError / network failure) -> Rule 7
    2. SOP status is not 'PUBLISHED' (e.g. DEACTIVATED, SUPERSEDED, DRAFT) -> Rule 5
    3. The Hub canonical SHA-256 hash has changed since plan creation -> Edge Case 4
    """
    if hub_service is None:
        hub_service = MockHubService()

    try:
        status_info = hub_service.get_sop_status(sop_id)
    except Exception as e:
        # Rule 7: Fail closed when Hub is unreachable
        return PreStepGuardResult(
            passed=False,
            reason=f"Hub unreachable during pre-mutation check: {str(e)}",
        )

    current_status = status_info.get("status")
    if current_status != "PUBLISHED":
        return PreStepGuardResult(
            passed=False,
            reason=f"SOP {sop_id} is in invalid state '{current_status}'. Only 'PUBLISHED' SOPs may mutate systems.",
        )

    current_hash = status_info.get("canonical_hash")
    if current_hash != expected_canonical_hash:
        return PreStepGuardResult(
            passed=False,
            reason=(
                f"SOP {sop_id} hash mismatch detected! Expected '{expected_canonical_hash}', "
                f"but Hub reported '{current_hash}'. SOP was modified after plan creation."
            ),
        )

    return PreStepGuardResult(passed=True, reason="SOP is PUBLISHED and hash is verified")

