import datetime
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from dataclasses import asdict

from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.dto.submission import SubmissionDTO, ReviewDTO
from submission_service.app.config import Settings


class SubmissionsDB(SubmissionsDBInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger
    ) -> None:
        self.client = client[settings.mongo_settings.name]
        self.settings = settings
        self.logger = logger
        self.db = self.client["submissions"]

    async def create_submission(self, submission: SubmissionDTO) -> bool:
        try:
            await self.db.insert_one(asdict(submission))
            return True

        except Exception:
            self.logger.exception("Exception when creating submission")
            return False

    async def get_submission_by_id(self, submission_id: int) -> SubmissionDTO | None:
        try:
            doc = await self.db.find_one({"submission_id": submission_id})
            if doc is None:
                return None

            return self._doc_to_template(doc)

        except Exception:
            self.logger.exception("Exception when getting submission by id")
            return None

    async def get_all_task_submissions(self, user_id: int, task_id: int) -> list[SubmissionDTO] | None:
        try:
            doc = await self.db.find({"user_id": user_id, "task_id": task_id}).to_list(None)
            if doc is None:
                return None

            submissions = []
            for d in doc:
                submissions.append(self._doc_to_template(d))

            return submissions

        except Exception:
            self.logger.exception("Exception when getting all task submissions")
            return None

    async def update_submission_with_review(
            self,
            submission_id: int,
            review: ReviewDTO | None,
            status: str,
    ) -> bool:
        try:
            await self.db.update_one(
                {"submission_id": submission_id},
                {"$set": {
                    "review": review,
                    "status": status,
                    "reviewed_at": datetime.datetime.now()
                }}
            )
            return True

        except Exception:
            self.logger.exception("Exception when updating submission with review")
            return False

    @staticmethod
    def _doc_to_template(doc: Any) -> SubmissionDTO:
        d = dict(doc)
        d.pop("_id", None)

        review = d.pop("review", None)
        if review:
            review = ReviewDTO(
                score=review["score"],
                feedback=review["feedback"],
                suggestions=review["suggestions"],
            )

        d["review"] = review
        return SubmissionDTO(**d)
