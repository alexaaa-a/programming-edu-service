from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.dto.submission import SubmissionDTO


class GetTaskSubmissionsUseCase:
    def __init__(self, submissions_db: SubmissionsDBInterface) -> None:
        self.submissions_db = submissions_db

    async def __call__(self, task_id: int, user_id: int) -> list[SubmissionDTO] | None:
        return await self.submissions_db.get_all_task_submissions(user_id=user_id, task_id=task_id)
