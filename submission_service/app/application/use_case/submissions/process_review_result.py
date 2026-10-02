import logging
from typing import Literal

from submission_service.app.application.decisions import (
    read_tags,
    tagging_questions,
    tagging_state,
)
from submission_service.app.application.dto.submission import ReviewDTO, SkillShareDTO
from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.interfaces.decisions import DecisionModelInterface

ApplyOutcome = Literal["applied", "skipped", "error"]

_logger = logging.getLogger("submission_service.review_result")


class ProcessReviewResultUseCase:
    def __init__(
            self,
            submissions_db: SubmissionsDBInterface,
            decisions: DecisionModelInterface | None = None,
            task_cache: TaskCacheInterface | None = None,
            min_confidence: float = 0.6,
    ) -> None:
        self.submissions_db = submissions_db
        self._decisions = decisions
        self._task_cache = task_cache
        self._min_confidence = min_confidence

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
        if review is not None:
            await self._tag_skills(
                review,
                task_id=existing.task_id,
                user_id=existing.user_id,
            )
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

    async def _tag_skills(
            self,
            review: ReviewDTO,
            task_id: int | None,
            user_id: int | None,
    ) -> None:
        if self._decisions is None or not self._decisions.enabled:
            return
        criteria = [row for row in (review.criteria or []) if str(row.text or "").strip()]
        if not criteria:
            return
        texts = [
            " ".join(f"{row.text}. {row.note}".split()).strip() for row in criteria
        ]
        description = await self._task_description(task_id, user_id)
        try:
            answers = await self._decisions.ask(
                tagging_state(texts, task_description=description),
                tagging_questions(texts),
                label="skill_tagging",
            )
        except Exception:
            _logger.exception("skill tagging failed")
            return
        tags = read_tags(answers, count=len(texts), min_confidence=self._min_confidence)
        for index, shares in tags.items():
            criteria[index].skills = [
                SkillShareDTO(skill_id=skill_id, share=round(share, 4))
                for skill_id, share in shares
            ]
        if tags:
            _logger.info(
                "review.skills.tagged criteria=%s tagged=%s latency_ms=%.0f",
                len(texts),
                len(tags),
                answers.latency_ms,
            )

    async def _task_description(self, task_id: int | None, user_id: int | None) -> str | None:
        if task_id is None or user_id is None or self._task_cache is None:
            return None
        try:
            description = await self._task_cache.get_task_description(
                int(task_id), int(user_id)
            )
        except Exception:
            return None
        return (description or "").strip() or None
