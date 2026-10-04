from abc import abstractmethod
from typing import Protocol

from submission_service.app.application.dto.submission import SubmissionDTO, ReviewDTO


class SubmissionsDBInterface(Protocol):
    @abstractmethod
    async def create_submission(self, submission: SubmissionDTO) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_submission_by_id(self, submission_id: int) -> SubmissionDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def get_all_task_submissions(self, user_id: int, task_id: int) -> list[SubmissionDTO] | None:
        raise NotImplementedError

    @abstractmethod
    async def get_all_user_submissions(self, user_id: int) -> list[SubmissionDTO] | None:
        raise NotImplementedError

    async def get_reviewed_submissions(self, limit: int = 1000) -> list[SubmissionDTO]:
        return []

    @abstractmethod
    async def update_submission_with_review(
            self,
            submission_id: int,
            review: ReviewDTO | None,
            status: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def mark_submission_status(
            self,
            submission_id: int,
            status: str,
            from_status: str | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_submission(self, submission_id: int) -> bool:
        raise NotImplementedError
