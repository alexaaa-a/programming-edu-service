import asyncio
from datetime import datetime
from types import SimpleNamespace

from submission_service.app.application.dto.submission import ReviewDTO, SubmissionDTO
from submission_service.app.application.use_case.submissions.submit_solution import (
    SubmitSubmissionResult,
    SubmitSubmissionUseCase,
)


class FakeSubmissionDB:
    def __init__(self, existing: list[SubmissionDTO] | None = None) -> None:
        self.existing = existing or []
        self.created: list[SubmissionDTO] = []
        self.deleted: list[int] = []
        self.marked: list[tuple[int, str]] = []

    async def get_all_task_submissions(self, user_id: int, task_id: int):
        return list(self.existing)

    async def create_submission(self, submission: SubmissionDTO) -> bool:
        self.created.append(submission)
        self.existing.append(submission)
        return True

    async def delete_submission(self, submission_id: int) -> bool:
        self.deleted.append(submission_id)
        before = len(self.existing)
        self.existing = [s for s in self.existing if s.submission_id != submission_id]
        return len(self.existing) < before

    async def mark_submission_status(
            self,
            submission_id: int,
            status: str,
            from_status: str | None = None,
    ) -> bool:
        for item in self.existing:
            if item.submission_id != submission_id:
                continue
            if from_status is not None and item.status != from_status:
                return False
            item.status = status
            self.marked.append((submission_id, status))
            return True
        return False


class FakeTaskCache:
    def __init__(self, status: str = "in_progress") -> None:
        self.status = status

    async def get_status(self, task_id: int, user_id: int):
        return self.status

    async def get_task_description(self, task_id: int, user_id: int):
        return "Напиши validate_login"


class FakeProducer:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def produce_submission_created(self, **kwargs) -> None:
        self.events.append(kwargs)


def _settings(max_rounds: int = 2):
    return SimpleNamespace(review_loop_settings=SimpleNamespace(max_rounds=max_rounds))


def _submission(status: str, with_review: bool = False, submission_id: int = 1) -> SubmissionDTO:
    review = None
    if with_review:
        review = ReviewDTO(score=4, feedback="Нужно чинить except", suggestions=["лови ValueError"])
    return SubmissionDTO(
        submission_id=submission_id,
        user_id=7,
        task_id=11,
        code="def f():\n    pass\n",
        status=status,
        review=review,
        created_at=datetime.now(),
        reviewed_at=datetime.now() if with_review else None,
    )


def test_blocks_when_pending_exists():
    uc = SubmitSubmissionUseCase(
        submission_db=FakeSubmissionDB([_submission(status="pending")]),
        submission_event_producer=FakeProducer(),
        task_cache=FakeTaskCache(),
        settings=_settings(),
    )
    result = asyncio.run(uc(11, "code", 7))
    assert result == SubmitSubmissionResult(error="pending_exists")


def test_blocks_when_max_rounds_reached():
    existing = [
        _submission(status="reviewed", with_review=True, submission_id=1),
        _submission(status="reviewed", with_review=True, submission_id=2),
    ]
    uc = SubmitSubmissionUseCase(
        submission_db=FakeSubmissionDB(existing),
        submission_event_producer=FakeProducer(),
        task_cache=FakeTaskCache(),
        settings=_settings(max_rounds=2),
    )
    result = asyncio.run(uc(11, "code", 7))
    assert result == SubmitSubmissionResult(error="max_rounds")


def test_bought_round_allows_a_third_submit_only_for_that_task():
    existing = [
        _submission(status="reviewed", with_review=True, submission_id=1),
        _submission(status="reviewed", with_review=True, submission_id=2),
    ]

    class LimitCache(FakeTaskCache):
        async def get_round_limit(self, task_id: int, user_id: int):
            return 3

    uc = SubmitSubmissionUseCase(
        submission_db=FakeSubmissionDB(existing),
        submission_event_producer=FakeProducer(),
        task_cache=LimitCache(),
        settings=_settings(max_rounds=2),
    )
    result = asyncio.run(uc(11, "code", 7))
    assert result.error is None
    assert result.submission_id is not None


def test_second_attempt_includes_previous_feedback():
    producer = FakeProducer()
    db = FakeSubmissionDB([_submission(status="reviewed", with_review=True)])
    uc = SubmitSubmissionUseCase(
        submission_db=db,
        submission_event_producer=producer,
        task_cache=FakeTaskCache(),
        settings=_settings(),
    )
    result = asyncio.run(uc(11, "def fixed():\n    return 1\n", 7))
    assert result.error is None
    assert result.submission_id is not None
    assert producer.events[0]["attempt"] == 2
    assert "except" in (producer.events[0]["previous_feedback"] or "").lower()


def test_produce_failure_marks_pending_failed():
    class BoomProducer:
        async def produce_submission_created(self, **kwargs) -> None:
            raise RuntimeError("kafka down")

    db = FakeSubmissionDB()
    uc = SubmitSubmissionUseCase(
        submission_db=db,
        submission_event_producer=BoomProducer(),  # type: ignore[arg-type]
        task_cache=FakeTaskCache(),
        settings=_settings(),
    )
    result = asyncio.run(uc(11, "code", 7))
    assert result == SubmitSubmissionResult(error="produce_failed")
    assert db.marked and db.marked[0][1] == "failed"
    assert all(item.status != "pending" for item in db.existing)


def test_race_after_create_when_second_pending_appears():
    class RaceAfterCreate(FakeSubmissionDB):
        async def create_submission(self, submission: SubmissionDTO) -> bool:
            twin = _submission(status="pending", submission_id=submission.submission_id - 1)
            self.existing.append(twin)
            self.created.append(submission)
            self.existing.append(submission)
            return True

    db = RaceAfterCreate()
    producer = FakeProducer()
    uc = SubmitSubmissionUseCase(
        submission_db=db,
        submission_event_producer=producer,
        task_cache=FakeTaskCache(),
        settings=_settings(),
    )
    result = asyncio.run(uc(11, "code", 7))
    assert result == SubmitSubmissionResult(error="pending_exists")
    assert db.deleted
    assert not producer.events


def test_infra_failed_without_reviewed_at_does_not_burn_round():
    existing = [
        _submission(status="failed", with_review=False, submission_id=1),
    ]
    existing[0].reviewed_at = None
    producer = FakeProducer()
    db = FakeSubmissionDB(existing)
    uc = SubmitSubmissionUseCase(
        submission_db=db,
        submission_event_producer=producer,
        task_cache=FakeTaskCache(),
        settings=_settings(max_rounds=2),
    )
    result = asyncio.run(uc(11, "code", 7))
    assert result.error is None
    assert result.submission_id is not None
