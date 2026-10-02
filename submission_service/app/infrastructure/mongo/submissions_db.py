import datetime
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from dataclasses import asdict

from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.dto.submission import (
    ChallengeResultDTO,
    CriterionResultDTO,
    PathStepResultDTO,
    ReviewDTO,
    SkillShareDTO,
    SubmissionDTO,
)
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

    async def get_all_user_submissions(self, user_id: int) -> list[SubmissionDTO] | None:
        try:
            doc = await self.db.find({"user_id": user_id}).to_list(None)
            if doc is None:
                return None

            submissions = []
            for d in doc:
                submissions.append(self._doc_to_template(d))

            return submissions

        except Exception:
            self.logger.exception("Exception when getting all user submissions")
            return None

    async def update_submission_with_review(
            self,
            submission_id: int,
            review: ReviewDTO | None,
            status: str,
    ) -> bool:
        try:
            review_doc = asdict(review) if review is not None else None
            if review is not None:
                query: dict[str, Any] = {
                    "submission_id": submission_id,
                    "status": {"$in": ["pending", "failed"]},
                }
            else:
                query = {"submission_id": submission_id, "status": "pending"}
            result = await self.db.update_one(
                query,
                {"$set": {
                    "review": review_doc,
                    "status": status,
                    "reviewed_at": datetime.datetime.now(tz=datetime.timezone.utc)
                }}
            )
            return bool(getattr(result, "matched_count", 0))

        except Exception:
            self.logger.exception("Exception when updating submission with review")
            return False

    async def mark_submission_status(
            self,
            submission_id: int,
            status: str,
            from_status: str | None = None,
    ) -> bool:
        try:
            query: dict[str, Any] = {"submission_id": submission_id}
            if from_status is not None:
                query["status"] = from_status
            result = await self.db.update_one(query, {"$set": {"status": status}})
            return bool(getattr(result, "matched_count", 0))
        except Exception:
            self.logger.exception("Exception when marking submission status")
            return False

    async def delete_submission(self, submission_id: int) -> bool:
        try:
            result = await self.db.delete_one({"submission_id": submission_id})
            return bool(getattr(result, "deleted_count", 0))
        except Exception:
            self.logger.exception("Exception when deleting submission")
            return False

    @staticmethod
    def _doc_to_template(doc: Any) -> SubmissionDTO:
        d = dict(doc)
        d.pop("_id", None)

        review = d.pop("review", None)
        if review:
            raw_criteria = review.get("criteria") or []
            criteria: list[CriterionResultDTO] = []
            if isinstance(raw_criteria, list):
                for index, item in enumerate(raw_criteria, start=1):
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("text") or "").strip()
                    if not text:
                        continue
                    criteria.append(
                        CriterionResultDTO(
                            id=str(item.get("id") or f"c{index}"),
                            text=text,
                            passed=bool(item.get("passed")),
                            note=str(item.get("note") or "").strip(),
                            skills=_skills_from_doc(item.get("skills")),
                        )
                    )
            raw_challenges = review.get("challenges") or []
            challenges: list[ChallengeResultDTO] = []
            if isinstance(raw_challenges, list):
                for item in raw_challenges:
                    if isinstance(item, str):
                        text = item.strip()
                        if text:
                            challenges.append(ChallengeResultDTO(text=text))
                        continue
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("text") or "").strip()
                    if not text:
                        continue
                    severity = str(item.get("severity") or "medium").strip().lower()
                    if severity not in {"low", "medium", "high"}:
                        severity = "medium"
                    challenges.append(ChallengeResultDTO(text=text, severity=severity))
            raw_path = review.get("agent_path") or []
            agent_path: list[PathStepResultDTO] = []
            if isinstance(raw_path, list):
                for item in raw_path:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").strip()
                    if not name:
                        continue
                    agent_path.append(
                        PathStepResultDTO(
                            kind=str(item.get("kind") or "step").strip() or "step",
                            name=name,
                            status=str(item.get("status") or "ok").strip() or "ok",
                            detail=str(item.get("detail") or "").strip(),
                        )
                    )
            review = ReviewDTO(
                score=review["score"],
                feedback=review["feedback"],
                suggestions=review.get("suggestions") or [],
                criteria=criteria,
                challenges=challenges,
                agent_path=agent_path,
            )

        d["review"] = review
        return SubmissionDTO(**d)


def _skills_from_doc(raw: Any) -> list[SkillShareDTO]:
    if not isinstance(raw, list):
        return []
    shares: list[SkillShareDTO] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or "").strip()
        try:
            share = float(item.get("share"))
        except (TypeError, ValueError):
            continue
        if skill_id and share > 0.0:
            shares.append(SkillShareDTO(skill_id=skill_id, share=share))
    return shares
