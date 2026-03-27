from typing import Any, Protocol
import logging

from agent_service.app.application.dto import Review


class ReviewerAgentProtocol(Protocol):
    async def run(self, code: str, task_description: str) -> Review: ...


class BugAgentProtocol(Protocol):
    async def run(self, code: str) -> Review: ...


class MentorAgentProtocol(Protocol):
    async def run(self, code: str, results: Any) -> str: ...


class ReviewOrchestrator:
    def __init__(
        self,
        reviewer_agent: ReviewerAgentProtocol,
        bug_agent: BugAgentProtocol,
        mentor_agent: MentorAgentProtocol,
    ) -> None:
        self._reviewer_agent = reviewer_agent
        self._bug_agent = bug_agent
        self._mentor_agent = mentor_agent

    async def run(self, code: str, task_description: str) -> Review:
        logger = logging.getLogger("agent_service")
        trace_id = None
        try:
            from agent_service.app.application.observability.tracing import ensure_trace_id

            trace_id = ensure_trace_id()
        except Exception:
            trace_id = "unknown"

        logger.info("pipeline.trace trace_id=%s step=Reviewer start", trace_id)
        reviewer_review = await self._reviewer_agent.run(
            code=code,
            task_description=task_description,
        )
        logger.info(
            "pipeline.trace trace_id=%s step=Reviewer end score=%s",
            trace_id,
            reviewer_review.score,
        )

        logger.info("pipeline.trace trace_id=%s step=Bug start", trace_id)
        bug_review = await self._bug_agent.run(code=code)
        logger.info(
            "pipeline.trace trace_id=%s step=Bug end score=%s",
            trace_id,
            bug_review.score,
        )

        results: dict[str, Any] = {
            "reviewer_review": reviewer_review,
            "bug_review": bug_review,
        }

        logger.info("pipeline.trace trace_id=%s step=Mentor start", trace_id)
        try:
            final_feedback = await self._mentor_agent.run(
                code=code,
                results=results,
            )
            logger.info("pipeline.trace trace_id=%s step=Mentor end", trace_id)
        except Exception:
            logger.exception("pipeline.trace trace_id=%s step=Mentor error; using fallback feedback", trace_id)
            reviewer_feedback = reviewer_review.feedback.strip()
            bug_feedback = bug_review.feedback.strip()
            parts = [p for p in [reviewer_feedback, bug_feedback] if p]
            final_feedback = "\n\n".join(parts) if parts else "Review completed with fallback feedback."

        score = round((reviewer_review.score + bug_review.score) / 2)
        suggestions = list(
            dict.fromkeys(
                reviewer_review.suggestions + bug_review.suggestions,
            ),
        )

        return Review(
            score=score,
            feedback=final_feedback,
            suggestions=suggestions,
        )
