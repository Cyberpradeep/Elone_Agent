"""Unit and Contract Tests for Autonomy Subsystem & Scorecard Engine (Module A9).

Verifies:
- 10-run consecutive success qualification gate for Policy-Based mode.
- Immediate automatic demotion upon single execution or verification failure.
- ModeRouter behavior across Shadow, Supervised, and Policy-Based modes.
- Strict mode rejection with UnqualifiedAutonomyError.
- Thread safety under concurrent run recording.
"""

import threading
import pytest
from orchestrator.state_graph import ExecutionModeEnum
from autonomy.scorecard import AutonomyScorecard, QUALIFICATION_THRESHOLD
from autonomy.modes import ModeRouter, UnqualifiedAutonomyError


def test_consecutive_success_increments_and_qualification():
    """Verify that consecutive successes increment and reach qualification at exactly 10 runs."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    sop_id = "SOP-WIN-014"

    # Runs 1 through 9: Not yet qualified
    for i in range(1, 10):
        rec = scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)
        assert rec.consecutive_successes == i
        assert rec.successful_runs == i
        assert rec.total_runs == i
        assert rec.is_qualified is False
        assert scorecard.is_qualified_for_policy_mode(sop_id) is False

    # Run 10: Qualifies for Policy-Based mode
    rec10 = scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)
    assert rec10.consecutive_successes == 10
    assert rec10.is_qualified is True
    assert scorecard.is_qualified_for_policy_mode(sop_id) is True


def test_failure_triggers_immediate_demotion():
    """Verify that any single failure immediately resets counter to 0 and demotes SOP."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    sop_id = "SOP-WIN-014"

    # Qualify the SOP with 10 successes
    for _ in range(10):
        scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)
    assert scorecard.is_qualified_for_policy_mode(sop_id) is True

    # 11th run fails due to service restart timeout
    demoted_rec = scorecard.record_run(
        sop_id,
        success=False,
        mode=ExecutionModeEnum.POLICY_BASED,
        reason="WinRM timeout during Spooler restart",
    )

    # Must immediately demote
    assert demoted_rec.consecutive_successes == 0
    assert demoted_rec.is_qualified is False
    assert demoted_rec.failed_runs == 1
    assert demoted_rec.last_demoted_at is not None
    assert "WinRM timeout" in demoted_rec.last_demoted_reason
    assert scorecard.is_qualified_for_policy_mode(sop_id) is False


def test_manual_demotion():
    """Verify manual operator demotion resets qualification."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    sop_id = "SOP-NET-006"

    for _ in range(10):
        scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)
    assert scorecard.is_qualified_for_policy_mode(sop_id) is True

    demoted = scorecard.demote(sop_id, reason="Security audit policy update")
    assert demoted.consecutive_successes == 0
    assert demoted.is_qualified is False
    assert demoted.last_demoted_reason == "Security audit policy update"


def test_shadow_mode_does_not_increment_operational_consecutive_successes():
    """Verify that simulation runs in Shadow mode do not count toward operational qualification."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    sop_id = "SOP-DB-021"

    rec = scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SHADOW)
    assert rec.total_runs == 1
    assert rec.successful_runs == 1
    # Consecutive operational successes must remain 0
    assert rec.consecutive_successes == 0
    assert rec.is_qualified is False


def test_mode_router_fallback_for_unqualified_sop():
    """Verify ModeRouter safely falls back to Supervised mode when SOP is unqualified."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    router = ModeRouter(scorecard=scorecard, strict_enforcement=False)
    sop_id = "SOP-WIN-014"

    # Only 3 successful runs completed
    for _ in range(3):
        scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)

    resolved_mode, msg = router.resolve_mode(sop_id, requested_mode=ExecutionModeEnum.POLICY_BASED)
    assert resolved_mode == ExecutionModeEnum.SUPERVISED
    assert "Falling back safely to Supervised mode" in msg


def test_mode_router_authorizes_qualified_sop():
    """Verify ModeRouter authorizes Policy-Based mode when SOP has 10 consecutive successes."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    router = ModeRouter(scorecard=scorecard, strict_enforcement=False)
    sop_id = "SOP-WIN-014"

    # Qualify with 10 runs
    for _ in range(10):
        scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)

    resolved_mode, msg = router.resolve_mode(sop_id, requested_mode=ExecutionModeEnum.POLICY_BASED)
    assert resolved_mode == ExecutionModeEnum.POLICY_BASED
    assert "Policy-based autonomy authorized" in msg


def test_mode_router_strict_enforcement_raises_error():
    """Verify ModeRouter in strict enforcement raises UnqualifiedAutonomyError."""
    scorecard = AutonomyScorecard(qualification_threshold=10)
    router = ModeRouter(scorecard=scorecard, strict_enforcement=True)
    sop_id = "SOP-BKP-003"

    with pytest.raises(UnqualifiedAutonomyError, match="unqualified for Policy-Based mode"):
        router.resolve_mode(sop_id, requested_mode=ExecutionModeEnum.POLICY_BASED)


def test_concurrent_scorecard_thread_safety():
    """Verify thread safety under concurrent run reports across multiple threads."""
    scorecard = AutonomyScorecard(qualification_threshold=100)
    sop_id = "SOP-CONCURRENT-001"

    def worker():
        for _ in range(25):
            scorecard.record_run(sop_id, success=True, mode=ExecutionModeEnum.SUPERVISED)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rec = scorecard.get_scorecard(sop_id)
    assert rec.total_runs == 100
    assert rec.successful_runs == 100
    assert rec.consecutive_successes == 100
    assert rec.is_qualified is True
