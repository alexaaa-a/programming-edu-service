from typing import Protocol

from agent_service.app.application.eval import (
    ReviewEvaluationRunSummary,
)


class EvalRunRepository(Protocol):
    async def save_run(self, summary: ReviewEvaluationRunSummary) -> None:
        raise NotImplementedError

    async def get_run(self, run_id: str) -> ReviewEvaluationRunSummary | None:
        raise NotImplementedError
