from dataclasses import dataclass

from agent_service.app.application.dto import Review
from agent_service.app.application.orchestrators import ReviewOrchestrator
from agent_service.app.application.observability.tracing import ensure_trace_id
from agent_service.app.application.observability.llm_trace import (
    LlmTracer,
    clip_for_trace,
    get_noop_tracer,
    trace_async,
)


@dataclass(frozen=True, slots=True)
class ReviewSubmissionResult:
    submission_id: str
    review: Review


class ReviewSubmissionUseCase:
    def __init__(
            self,
            orchestrator: ReviewOrchestrator,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._tracer = tracer or get_noop_tracer()

    async def __call__(
            self,
            submission_id: str,
            code: str,
            task_description: str,
            task_id: str | None = None,
            user_id: str | None = None,
            attempt: int | None = None,
            previous_feedback: str | None = None,
    ) -> ReviewSubmissionResult:
        ensure_trace_id()

        async def _run() -> Review:
            return await self._orchestrator.run(
                code=code,
                task_description=task_description,
                task_id=task_id,
                submission_id=submission_id,
                user_id=user_id,
                attempt=attempt,
                previous_feedback=previous_feedback,
            )

        review = await trace_async(
            self._tracer,
            "review-submission",
            _run,
            as_type="chain",
            user_id=user_id,
            session_id=str(submission_id),
            tags=["review", "mas"],
            input={
                "submission_id": submission_id,
                "task_id": task_id,
                "attempt": attempt,
                "task_description": clip_for_trace(task_description, max_chars=1200),
                "code": clip_for_trace(code, max_chars=2500),
                "previous_feedback": clip_for_trace(previous_feedback or "", max_chars=800),
            },
            metadata={
                "submission_id": submission_id,
                "task_id": task_id or "",
                "attempt": attempt or 1,
                "code_len": len(code),
            },
            output_from=lambda item: {
                "score": item.score,
                "feedback": clip_for_trace(item.feedback, max_chars=1800),
                "suggestions": list(item.suggestions)[:8],
                "criteria_passed": sum(1 for row in item.criteria if row.passed),
                "criteria_total": len(item.criteria),
                "path": [step.name for step in item.agent_path],
            },
            metadata_from=lambda item: {
                "score": item.score,
                "suggestions": len(item.suggestions),
                "challenges": len(item.challenges),
            },
            scores_from=lambda item: (
                ("review_score", item.score, {"comment": "scorecard.final"}),
                (
                    "criteria_pass_rate",
                    (sum(1 for row in item.criteria if row.passed) / len(item.criteria))
                    if item.criteria
                    else 1.0,
                    {"comment": "acceptance criteria"},
                ),
            ),
            flush=True,
        )
        return ReviewSubmissionResult(submission_id=submission_id, review=review)
