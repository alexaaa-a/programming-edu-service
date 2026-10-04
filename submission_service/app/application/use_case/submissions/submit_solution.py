import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from submission_service.app.application.dto.submission import SubmissionDTO
from submission_service.app.config import Settings
from submission_service.app.application.interfaces.db.submissions_db import (
    SubmissionsDBInterface,
)
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.interfaces.kafka import (
    SubmissionEventProducerInterface,
)


@dataclass(frozen=True, slots=True)
class SubmitSubmissionResult:
    submission_id: int | None = None
    error: str | None = None


class SubmitSubmissionUseCase:
    ALLOWED_STATUSES_FOR_SUBMISSION = ("in_progress", "review")

    def __init__(
            self,
            submission_db: SubmissionsDBInterface,
            submission_event_producer: SubmissionEventProducerInterface,
            task_cache: TaskCacheInterface,
            settings: Settings,
    ) -> None:
        self.submission_db = submission_db
        self.submission_event_producer = submission_event_producer
        self.task_cache = task_cache
        self._max_rounds = max(1, int(settings.review_loop_settings.max_rounds))

    async def __call__(self, task_id: int, code: str, user_id: int) -> SubmitSubmissionResult:
        status = await self.task_cache.get_status(task_id, user_id)
        if status is None or status not in self.ALLOWED_STATUSES_FOR_SUBMISSION:
            return SubmitSubmissionResult(error="task_not_ready")

        existing = await self.submission_db.get_all_task_submissions(user_id, task_id) or []
        if any(item.status == "pending" for item in existing):
            return SubmitSubmissionResult(error="pending_exists")
        counted = [item for item in existing if _counts_toward_rounds(item)]
        cap = await self._round_cap(task_id, user_id)
        if len(counted) >= cap:
            return SubmitSubmissionResult(error="max_rounds")

        previous = _latest_reviewed(existing)
        attempt = len(counted) + 1
        previous_feedback = None
        if previous is not None and previous.review is not None:
            previous_feedback = _format_previous_feedback(previous.review)

        task_description = await self.task_cache.get_task_description(task_id, user_id)
        task_description = task_description or ""
        hidden_tests = await self._task_tests(task_id, user_id)
        submission = SubmissionDTO(
            submission_id=self._generate_submission_id(),
            user_id=user_id,
            task_id=task_id,
            code=code,
            status="pending",
            review=None,
            created_at=datetime.now(tz=timezone.utc),
            reviewed_at=None,
        )

        create_submission = await self.submission_db.create_submission(submission)
        if not create_submission:
            return SubmitSubmissionResult(error="create_failed")

        after = await self.submission_db.get_all_task_submissions(user_id, task_id) or []
        pending = [item for item in after if item.status == "pending"]
        if len(pending) > 1:
            winner_id = min(item.submission_id for item in pending)
            if submission.submission_id != winner_id:
                await self.submission_db.delete_submission(submission.submission_id)
                return SubmitSubmissionResult(error="pending_exists")
            for item in pending:
                if item.submission_id != winner_id:
                    await self.submission_db.delete_submission(item.submission_id)

        completed = [item for item in after if _counts_toward_rounds(item)]
        if len(completed) >= cap:
            await self.submission_db.delete_submission(submission.submission_id)
            return SubmitSubmissionResult(error="max_rounds")

        try:
            await self.submission_event_producer.produce_submission_created(
                submission_id=submission.submission_id,
                task_id=task_id,
                user_id=user_id,
                code=code,
                task_description=task_description,
                attempt=attempt,
                previous_feedback=previous_feedback,
                hidden_tests=hidden_tests,
            )
        except Exception:
            marked = await self.submission_db.mark_submission_status(
                submission.submission_id,
                "failed",
                from_status="pending",
            )
            if not marked:
                await self.submission_db.delete_submission(submission.submission_id)
            return SubmitSubmissionResult(error="produce_failed")
        return SubmitSubmissionResult(submission_id=submission.submission_id)

    async def _task_tests(self, task_id: int, user_id: int) -> str | None:
        getter = getattr(self.task_cache, "get_task_tests", None)
        if getter is None:
            return None
        try:
            return await getter(task_id, user_id)
        except Exception:
            return None

    async def _round_cap(self, task_id: int, user_id: int) -> int:
        getter = getattr(self.task_cache, "get_round_limit", None)
        if getter is None:
            return self._max_rounds
        try:
            raw = await getter(task_id, user_id)
        except Exception:
            return self._max_rounds
        if isinstance(raw, int) and raw > self._max_rounds:
            return min(raw, self._max_rounds + 1)
        return self._max_rounds

    @staticmethod
    def _generate_submission_id() -> int:
        return uuid.uuid4().int % (2**53)


def _counts_toward_rounds(item: SubmissionDTO) -> bool:
    if item.status == "pending":
        return False
    if item.review is not None:
        return True
    if item.status == "failed" and item.reviewed_at is not None:
        return True
    return False


def _latest_reviewed(submissions: list[SubmissionDTO]) -> SubmissionDTO | None:
    reviewed = [item for item in submissions if item.review is not None]
    if not reviewed:
        return None
    return max(reviewed, key=lambda item: item.created_at)


def _format_previous_feedback(review) -> str:
    bits = [f"Скор {review.score}/10.", (review.feedback or "").strip()]
    if review.suggestions:
        bits.append("Правки: " + "; ".join(review.suggestions[:6]))
    return " ".join(part for part in bits if part).strip()
