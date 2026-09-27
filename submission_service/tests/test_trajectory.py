from datetime import datetime, timedelta, timezone
import asyncio
from types import SimpleNamespace

from submission_service.app.application.use_case.submissions.get_user_trajectory import (
    GetUserTrajectoryUseCase,
)
from submission_service.app.application.dto.submission import (
    CriterionResultDTO,
    ReviewDTO,
    SubmissionDTO,
)
from submission_service.app.application.trajectory.formula import (
    TrajectoryConfig,
    compute_trajectory,
    normalize_score,
)


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def _review(score: int, criteria: list[tuple[str, bool]] | None = None) -> ReviewDTO:
    items = [
        CriterionResultDTO(id=f"c{i}", text=text, passed=passed)
        for i, (text, passed) in enumerate(criteria or [])
    ]
    return ReviewDTO(
        score=score,
        feedback="ok" if score >= 8 else "нужны правки",
        suggestions=[],
        criteria=items,
    )


def _sub(
        task_id: int,
        score: int | None,
        created_at: datetime,
        submission_id: int = 1,
        status: str = "reviewed",
        criteria: list[tuple[str, bool]] | None = None,
) -> SubmissionDTO:
    review = None if score is None else _review(score, criteria)
    return SubmissionDTO(
        submission_id=submission_id,
        user_id=7,
        task_id=task_id,
        code="print(1)",
        status="pending" if score is None and status == "pending" else status,
        review=review,
        created_at=created_at,
        reviewed_at=created_at if review is not None else None,
    )


def test_normalize_score_accepts_ten_and_hundred():
    assert normalize_score(8) == 8
    assert normalize_score(80) == 8
    assert normalize_score(-1) == 0
    assert normalize_score(12) == 1.2


def test_empty_history_starts_path():
    result = compute_trajectory([], now=NOW)
    assert result.action == "start"
    assert result.mastery == 0
    assert result.block_close is True
    assert result.block_next_sprint is True


def test_pending_submission_waits():
    result = compute_trajectory(
        [_sub(task_id=1, score=None, created_at=NOW, status="pending")],
        now=NOW,
        task_id=1,
    )
    assert result.action == "wait_review"
    assert result.block_close is True


def test_low_score_first_attempt_asks_chat():
    result = compute_trajectory(
        [_sub(task_id=1, score=3, created_at=NOW, submission_id=1)],
        now=NOW,
        task_id=1,
    )
    assert result.action == "chat"
    assert result.block_close is True
    assert result.block_next_sprint is True
    assert result.current_attempts == 1
    assert result.current_score == 3


def test_mid_score_first_attempt_asks_revise():
    result = compute_trajectory(
        [
            _sub(
                task_id=1,
                score=6,
                created_at=NOW,
                criteria=[("вернуть сумму", True), ("проверить типы", True)],
            )
        ],
        now=NOW,
        task_id=1,
    )
    assert result.action == "revise"
    assert result.block_close is True


def test_broken_syntax_does_not_unlock_sprint():
    result = compute_trajectory(
        [_sub(task_id=11, score=2, created_at=NOW)],
        now=NOW,
        task_id=11,
    )
    assert result.readiness < 0.7
    assert result.action in {"chat", "revise"}
    assert result.block_next_sprint is True


def test_second_weak_attempt_closes_weak():
    earlier = NOW - timedelta(hours=2)
    result = compute_trajectory(
        [
            _sub(task_id=1, score=4, created_at=earlier, submission_id=1),
            _sub(task_id=1, score=5, created_at=NOW, submission_id=2),
        ],
        now=NOW,
        task_id=1,
        config=TrajectoryConfig(max_rounds=2),
    )
    assert result.action == "close_weak"
    assert result.block_close is False
    assert result.block_next_sprint is False
    assert result.current_attempts == 2
    assert result.difficulty > 0


def test_infra_failed_does_not_count_toward_attempts():
    earlier = NOW - timedelta(hours=1)
    infra = SubmissionDTO(
        submission_id=1,
        user_id=7,
        task_id=1,
        code="x",
        status="failed",
        review=None,
        created_at=earlier,
        reviewed_at=None,
    )
    scored = _sub(task_id=1, score=5, created_at=NOW, submission_id=2)
    result = compute_trajectory(
        [infra, scored],
        now=NOW,
        task_id=1,
        config=TrajectoryConfig(max_rounds=2),
    )
    assert result.current_attempts == 1
    assert result.action in {"chat", "revise"}


def test_high_score_and_checklist_allows_close():
    result = compute_trajectory(
        [
            _sub(
                task_id=3,
                score=9,
                created_at=NOW,
                criteria=[("сумма", True), ("тесты", True)],
            )
        ],
        now=NOW,
        task_id=3,
        current_task_status="review",
    )
    assert result.action == "close_ok"
    assert result.block_close is False
    assert result.mastery >= 0.75
    assert result.block_next_sprint is False


def test_empty_task_status_with_pass_score_does_not_false_hold():
    result = compute_trajectory(
        [
            _sub(
                task_id=3,
                score=9,
                created_at=NOW,
                criteria=[("сумма", True)],
            )
        ],
        now=NOW,
        task_id=3,
        current_task_status="",
    )
    assert "неизвестен" not in result.reason.lower()
    assert "синхрон" not in result.reason.lower()
    done = compute_trajectory(
        [
            _sub(
                task_id=3,
                score=9,
                created_at=NOW,
                criteria=[("сумма", True)],
            )
        ],
        now=NOW,
        task_id=3,
        current_task_status="done",
    )
    assert result.action == done.action
    assert result.block_next_sprint == done.block_next_sprint


def test_strong_window_on_done_task_suggests_next_sprint():
    result = compute_trajectory(
        [
            _sub(
                task_id=1,
                score=9,
                created_at=NOW - timedelta(days=1),
                submission_id=1,
                criteria=[("a", True)],
            ),
            _sub(
                task_id=2,
                score=8,
                created_at=NOW - timedelta(hours=3),
                submission_id=2,
                criteria=[("b", True)],
            ),
            _sub(
                task_id=3,
                score=9,
                created_at=NOW,
                submission_id=3,
                criteria=[("c", True)],
            ),
        ],
        now=NOW,
        task_id=3,
        current_task_status="done",
    )
    assert result.action == "next_sprint"
    assert result.block_next_sprint is False
    assert result.readiness >= 0.75


def test_retries_raise_difficulty_and_hold_sprint():
    t0 = NOW - timedelta(days=1)
    result = compute_trajectory(
        [
            _sub(task_id=1, score=4, created_at=t0, submission_id=1),
            _sub(task_id=1, score=8, created_at=t0 + timedelta(hours=2), submission_id=2),
            _sub(task_id=2, score=3, created_at=t0 + timedelta(hours=4), submission_id=3),
            _sub(task_id=2, score=8, created_at=t0 + timedelta(hours=5), submission_id=4),
            _sub(task_id=3, score=4, created_at=NOW, submission_id=5),
        ],
        now=NOW,
        task_id=2,
        current_task_status="done",
    )
    assert result.difficulty > 0.4
    assert result.readiness < 0.7
    assert result.action == "next_sprint"
    assert result.block_next_sprint is False


def test_recent_scores_weigh_more_than_old():
    old = compute_trajectory(
        [
            _sub(task_id=1, score=9, created_at=NOW - timedelta(days=10), submission_id=1),
            _sub(task_id=2, score=3, created_at=NOW, submission_id=2),
        ],
        now=NOW,
    )
    fresh = compute_trajectory(
        [
            _sub(task_id=1, score=3, created_at=NOW - timedelta(days=10), submission_id=1),
            _sub(task_id=2, score=9, created_at=NOW, submission_id=2),
        ],
        now=NOW,
    )
    assert fresh.mastery > old.mastery


def test_stale_activity_lowers_pace():
    stale = compute_trajectory(
        [_sub(task_id=1, score=9, created_at=NOW - timedelta(days=10))],
        now=NOW,
    )
    fresh = compute_trajectory(
        [_sub(task_id=1, score=9, created_at=NOW - timedelta(hours=3))],
        now=NOW,
    )
    assert fresh.pace > stale.pace


def test_use_case_reads_submissions_and_task_status():
    class FakeDB:
        async def get_all_user_submissions(self, user_id: int):
            assert user_id == 7
            return [_sub(task_id=9, score=9, created_at=NOW, criteria=[("сумма", True)])]

    class FakeCache:
        async def get_status(self, task_id: int, user_id: int):
            assert task_id == 9
            return "review"

    uc = GetUserTrajectoryUseCase(
        submissions_db=FakeDB(),
        settings=SimpleNamespace(review_loop_settings=SimpleNamespace(max_rounds=2)),
        task_cache=FakeCache(),
    )
    result = asyncio.run(uc(user_id=7, task_id=9, now=NOW))
    assert result.action == "close_ok"
    assert result.current_task_id == 9
    assert result.block_close is False
