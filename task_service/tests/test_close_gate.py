from datetime import datetime, timezone

from task_service.app.application.close_gate import ReviewSnapshot, evaluate_close, normalize_score


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _snap(
    score: float | None,
    *,
    status: str = "reviewed",
    created_at: datetime | None = None,
    reviewed_at: datetime | str | None = ...,
) -> ReviewSnapshot:
    if reviewed_at is ...:
        reviewed_at = NOW if score is not None or status == "failed" else None
    return ReviewSnapshot(
        status=status,
        score=score,
        created_at=created_at or NOW,
        reviewed_at=reviewed_at,
    )


def test_normalize_percent_scores():
    assert normalize_score(80) == 8.0
    assert normalize_score(8) == 8.0


def test_blocks_without_review():
    decision = evaluate_close([])
    assert decision.allowed is False
    assert decision.code == "need_review"


def test_blocks_pending():
    decision = evaluate_close([_snap(None, status="pending", reviewed_at=None)])
    assert decision.allowed is False
    assert decision.code == "pending"


def test_blocks_weak_first_attempt():
    decision = evaluate_close([_snap(5)])
    assert decision.allowed is False
    assert decision.code == "revise"
    assert decision.quality is None


def test_allows_weak_when_attempts_exhausted():
    decision = evaluate_close([_snap(4), _snap(6)])
    assert decision.allowed is True
    assert decision.quality == "weak"
    assert decision.code == "weak"


def test_failed_attempt_counts_toward_max_rounds():
    decision = evaluate_close([_snap(None, status="failed"), _snap(5)])
    assert decision.allowed is True
    assert decision.code == "weak"


def test_single_agent_failure_asks_revise():
    decision = evaluate_close([_snap(None, status="failed")])
    assert decision.allowed is False
    assert decision.code == "revise"


def test_two_agent_failures_allow_weak_close():
    decision = evaluate_close(
        [_snap(None, status="failed"), _snap(None, status="failed")]
    )
    assert decision.allowed is True
    assert decision.quality == "weak"


def test_infra_failed_without_reviewed_at_does_not_burn_round():
    decision = evaluate_close(
        [
            _snap(None, status="failed", reviewed_at=None),
            _snap(None, status="failed", reviewed_at=None),
            _snap(5),
        ]
    )
    # Two infra fails + one weak score → still revise (spent=1)
    assert decision.allowed is False
    assert decision.code == "revise"


def test_two_infra_failures_do_not_unlock_weak():
    decision = evaluate_close(
        [
            _snap(None, status="failed", reviewed_at=None),
            _snap(None, status="failed", reviewed_at=None),
        ]
    )
    assert decision.allowed is False
    assert decision.code == "revise"


def test_allows_ok_on_pass_score():
    decision = evaluate_close([_snap(8)])
    assert decision.allowed is True
    assert decision.quality == "ok"


def test_percent_score_counts_as_pass():
    decision = evaluate_close([_snap(90)])
    assert decision.allowed is True
    assert decision.quality == "ok"


def test_pending_beats_previous_pass():
    decision = evaluate_close(
        [_snap(9), _snap(None, status="pending", reviewed_at=None)]
    )
    assert decision.allowed is False
    assert decision.code == "pending"
