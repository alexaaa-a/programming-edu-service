from datetime import datetime, timedelta, timezone

from submission_service.app.application.dto.submission import ReviewDTO, SubmissionDTO
from submission_service.app.application.trajectory.formula import compute_trajectory
from submission_service.app.application.trajectory.nudge import (
    SILENCE_HOURS,
    detect_nudge,
    similarity,
)


NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

CODE = """def order_total(items, promo=0):
    total = sum(item["price"] * item["qty"] for item in items)
    return total - total * promo // 100
"""

CODE_SAME_BUT_TIDIER = """# считаем итог
def order_total(items, promo=0):
    total = sum(item["price"] * item["qty"] for item in items)

    return total - total * promo // 100
"""

CODE_FIXED = """def order_total(items, promo=0):
    if not 0 <= promo <= 100:
        raise ValueError("promo")
    total = sum(item["price"] * item["qty"] for item in items)
    return total - total * promo // 100
"""


def _submission(
        submission_id: int,
        code: str,
        at: datetime,
        score: int | None = None,
        task_id: int = 1,
) -> SubmissionDTO:
    review = (
        ReviewDTO(score=score, feedback="", suggestions=[], criteria=[])
        if score is not None
        else None
    )
    return SubmissionDTO(
        submission_id=submission_id,
        user_id=7,
        task_id=task_id,
        code=code,
        status="reviewed" if score is not None else "pending",
        review=review,
        created_at=at,
        reviewed_at=at if score is not None else None,
    )


def test_the_same_code_submitted_twice_is_a_signal():
    rows = [
        _submission(1, CODE, NOW - timedelta(hours=3), score=5),
        _submission(2, CODE_SAME_BUT_TIDIER, NOW - timedelta(minutes=10)),
    ]
    signal = detect_nudge(rows, now=NOW)
    assert signal is not None
    assert signal.kind == "repeat"
    assert signal.task_id == 1
    assert signal.score == 5


def test_a_real_fix_is_not_a_repeat():
    rows = [
        _submission(1, CODE, NOW - timedelta(hours=3), score=5),
        _submission(2, CODE_FIXED, NOW - timedelta(minutes=10)),
    ]
    assert detect_nudge(rows, now=NOW) is None


def test_the_same_code_on_another_task_is_not_a_repeat():
    rows = [
        _submission(1, CODE, NOW - timedelta(hours=3), score=5, task_id=1),
        _submission(2, CODE, NOW - timedelta(minutes=10), task_id=2),
    ]
    assert detect_nudge(rows, now=NOW) is None


def test_whitespace_and_comments_are_not_changes():
    assert similarity(CODE, CODE_SAME_BUT_TIDIER) == 1.0
    assert similarity(CODE, CODE_FIXED) < 0.97
    assert similarity("", "") == 1.0
    assert similarity("x = 1", "") == 0.0


def test_silence_after_a_failed_review_is_a_signal():
    rows = [_submission(1, CODE, NOW - timedelta(hours=SILENCE_HOURS + 1), score=4)]
    signal = detect_nudge(rows, now=NOW)
    assert signal is not None
    assert signal.kind == "silence"
    assert signal.hours_since == SILENCE_HOURS + 1
    assert "новой сдачи нет" in signal.detail


def test_a_fresh_failure_is_not_silence_yet():
    rows = [_submission(1, CODE, NOW - timedelta(hours=1), score=4)]
    assert detect_nudge(rows, now=NOW) is None


def test_a_week_old_failure_is_not_worth_a_message():
    rows = [_submission(1, CODE, NOW - timedelta(days=7), score=4)]
    assert detect_nudge(rows, now=NOW) is None


def test_a_passing_review_is_never_a_signal():
    rows = [_submission(1, CODE, NOW - timedelta(hours=12), score=9)]
    assert detect_nudge(rows, now=NOW) is None


def test_a_submission_still_waiting_for_review_is_not_a_signal():
    rows = [_submission(1, CODE, NOW - timedelta(hours=12))]
    assert detect_nudge(rows, now=NOW) is None


def test_scores_out_of_a_hundred_are_normalised():
    rows = [_submission(1, CODE, NOW - timedelta(hours=12), score=90)]
    assert detect_nudge(rows, now=NOW) is None


def test_no_submissions_no_signal():
    assert detect_nudge([], now=NOW) is None
    assert detect_nudge(None, now=NOW) is None


def test_a_repeat_wins_over_silence():
    rows = [
        _submission(1, CODE, NOW - timedelta(days=1), score=4),
        _submission(2, CODE, NOW - timedelta(hours=SILENCE_HOURS + 2), score=4),
    ]
    signal = detect_nudge(rows, now=NOW)
    assert signal is not None and signal.kind == "repeat"


def test_the_trajectory_carries_the_signal():
    rows = [
        _submission(1, CODE, NOW - timedelta(hours=3), score=5),
        _submission(2, CODE, NOW - timedelta(minutes=10)),
    ]
    result = compute_trajectory(rows, now=NOW)
    assert result.nudge is not None
    assert result.nudge.as_dict()["kind"] == "repeat"


def test_a_quiet_student_has_no_signal_in_the_trajectory():
    rows = [_submission(1, CODE, NOW - timedelta(minutes=5), score=9)]
    assert compute_trajectory(rows, now=NOW).nudge is None
