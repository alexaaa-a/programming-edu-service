from submission_service.app.application.dto.submission import ReviewDTO
from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface


class ProcessReviewResultUseCase:
    def __init__(self, submissions_db: SubmissionsDBInterface) -> None:
        self.submissions_db = submissions_db

    async def __call__(self, submission_id: int, review: ReviewDTO | None) -> bool:
        status = "reviewed" if review else "failed"

        updating = await self.submissions_db.update_submission_with_review(
            submission_id=submission_id,
            review=review,
            status=status
        )
        return updating
