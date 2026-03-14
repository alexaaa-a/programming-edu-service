import uuid
from datetime import datetime

from submission_service.app.application.dto.submission import SubmissionDTO
from submission_service.app.application.interfaces.db.submissions_db import (
    SubmissionsDBInterface,
)
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.interfaces.kafka import (
    SubmissionEventProducerInterface,
)


class SubmitSubmissionUseCase:
    ALLOWED_STATUSES_FOR_SUBMISSION = ("in_progress", "review")

    def __init__(
        self,
        submission_db: SubmissionsDBInterface,
        submission_event_producer: SubmissionEventProducerInterface,
        task_cache: TaskCacheInterface,
    ) -> None:
        self.submission_db = submission_db
        self.submission_event_producer = submission_event_producer
        self.task_cache = task_cache

    async def __call__(self, task_id: int, code: str, user_id: int) -> int | None:
        status = await self.task_cache.get_status(task_id, user_id)
        if status is None or status not in self.ALLOWED_STATUSES_FOR_SUBMISSION:
            return None
        submission = SubmissionDTO(
            submission_id=self._generate_submission_id(),
            user_id=user_id,
            task_id=task_id,
            code=code,
            status="pending",
            review=None,
            created_at=datetime.now(),
            reviewed_at=None
        )

        create_submission = await self.submission_db.create_submission(submission)
        if create_submission:
            await self.submission_event_producer.produce_submission_created(
                submission_id=submission.submission_id,
                task_id=task_id,
                user_id=user_id,
                code=code,
            )
            return submission.submission_id

        return None

    @staticmethod
    def _generate_submission_id() -> int:
        return uuid.uuid4().int % (2**53)
