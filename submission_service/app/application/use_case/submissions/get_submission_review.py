from submission_service.app.application.dto.submission import ReviewDTO
from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface


class GetSubmissionReviewUseCase:
    def __init__(self, submissions_db: SubmissionsDBInterface) -> None:
        self.submissions_db = submissions_db

    async def __call__(self, submission_id: int, user_id: int) -> ReviewDTO | None:
        submission = await self.submissions_db.get_submission_by_id(submission_id)
        if submission is None:
            return None

        if submission.user_id != user_id:
            return None

        return submission.review
