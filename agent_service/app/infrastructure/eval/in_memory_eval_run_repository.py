from typing import Dict

from agent_service.app.application.eval.interfaces.eval_repository import (
    EvalRunRepository,
)
from agent_service.app.application.eval import ReviewEvaluationRunSummary


class InMemoryEvalRunRepository(EvalRunRepository):
    def __init__(self) -> None:
        self._runs: Dict[str, ReviewEvaluationRunSummary] = {}

    async def save_run(self, summary: ReviewEvaluationRunSummary) -> None:
        self._runs[summary.run_id] = summary

    async def get_run(self, run_id: str) -> ReviewEvaluationRunSummary | None:
        return self._runs.get(run_id)
