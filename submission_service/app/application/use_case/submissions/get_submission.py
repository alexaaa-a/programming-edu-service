from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.dto.submission import SubmissionDTO


class GetSubmissionUseCase:
    def __init__(self, submission_db: SubmissionsDBInterface) -> None:
        self.submission_db = submission_db

    async def __call__(self, user_id: int, submission_id: int) -> SubmissionDTO | None:
        submission = await self.submission_db.get_submission_by_id(submission_id)
        if not submission:
            return None

        if submission.user_id != user_id:
            return None

        return submission
