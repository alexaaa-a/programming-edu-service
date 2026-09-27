import asyncio
from datetime import datetime
from pathlib import Path

from submission_service.app.application.dto.submission import ReviewDTO, SubmissionDTO
from submission_service.app.application.use_case.submissions.process_review_result import (
    ProcessReviewResultUseCase,
)


class FakeDB:
    def __init__(self, *, applied: bool = True, existing: SubmissionDTO | None = None) -> None:
        self.applied = applied
        self.calls = 0
        self.existing = existing

    async def get_submission_by_id(self, submission_id: int):
        return self.existing

    async def update_submission_with_review(
        self,
        submission_id: int,
        review: ReviewDTO | None,
        status: str,
    ) -> bool:
        self.calls += 1
        return self.applied


def _pending() -> SubmissionDTO:
    return SubmissionDTO(
        submission_id=1,
        user_id=7,
        task_id=11,
        code="x",
        status="pending",
        review=None,
        created_at=datetime.now(),
        reviewed_at=None,
    )


def test_process_review_returns_applied():
    db = FakeDB(applied=True, existing=_pending())
    uc = ProcessReviewResultUseCase(db)  # type: ignore[arg-type]
    review = ReviewDTO(score=8, feedback="ok", suggestions=[])
    assert asyncio_run(uc(1, review)) == "applied"
    assert db.calls == 1


def test_process_review_returns_skipped_when_not_pending():
    existing = _pending()
    existing.status = "reviewed"
    db = FakeDB(applied=False, existing=existing)
    uc = ProcessReviewResultUseCase(db)  # type: ignore[arg-type]
    assert asyncio_run(uc(1, None)) == "skipped"
    assert db.calls == 0


def test_process_review_returns_error_on_update_false_still_pending():
    db = FakeDB(applied=False, existing=_pending())
    uc = ProcessReviewResultUseCase(db)  # type: ignore[arg-type]
    assert asyncio_run(uc(1, None)) == "error"


def test_mongo_update_is_pending_only():
    text = (
        Path(__file__).resolve().parents[1]
        / "app/infrastructure/mongo/submissions_db.py"
    ).read_text(encoding="utf-8")
    assert '"status": "pending"' in text
    assert "matched_count" in text


def test_review_consumer_disables_auto_commit():
    text = (
        Path(__file__).resolve().parents[1]
        / "app/infrastructure/kafka/consumer.py"
    ).read_text(encoding="utf-8")
    assert "enable_auto_commit=False" in text
    assert text.count("enable_auto_commit=False") >= 2


def asyncio_run(coro):
    return asyncio.run(coro)
