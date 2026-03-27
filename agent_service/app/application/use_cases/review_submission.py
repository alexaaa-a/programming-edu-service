from dataclasses import dataclass

from agent_service.app.application.dto import Review
from agent_service.app.application.orchestrators import ReviewOrchestrator
from agent_service.app.application.observability.tracing import ensure_trace_id


@dataclass(frozen=True, slots=True)
class ReviewSubmissionResult:
    submission_id: str
    review: Review


class ReviewSubmissionUseCase:
    def __init__(self, orchestrator: ReviewOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def __call__(
        self,
        submission_id: str,
        code: str,
        task_description: str,
    ) -> ReviewSubmissionResult:
        ensure_trace_id()
        review = await self._orchestrator.run(
            code=code,
            task_description=task_description,
        )
        return ReviewSubmissionResult(submission_id=submission_id, review=review)
