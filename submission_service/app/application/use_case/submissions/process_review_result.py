from typing import Literal

from submission_service.app.application.dto.submission import ReviewDTO
from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface

ApplyOutcome = Literal["applied", "skipped", "error"]


class ProcessReviewResultUseCase:
    def __init__(self, submissions_db: SubmissionsDBInterface) -> None:
        self.submissions_db = submissions_db

    async def __call__(self, submission_id: int, review: ReviewDTO | None) -> ApplyOutcome:
        existing = await self.submissions_db.get_submission_by_id(submission_id)
        if existing is None:
            return "skipped"
        status_now = (existing.status or "").strip().lower()
        if status_now == "reviewed":
            return "skipped"
        if status_now == "failed" and review is None:
            return "skipped"
        if status_now not in {"pending", "failed"}:
            return "skipped"

        status = "reviewed" if review else "failed"
        try:
            updating = await self.submissions_db.update_submission_with_review(
                submission_id=submission_id,
                review=review,
                status=status,
            )
        except Exception:
            return "error"

        if updating:
            return "applied"

        again = await self.submissions_db.get_submission_by_id(submission_id)
        if again is not None and (again.status or "").strip().lower() == "reviewed":
            return "skipped"
        if again is not None and (again.status or "").strip().lower() != "pending":
            if review is None:
                return "skipped"
        return "error"
