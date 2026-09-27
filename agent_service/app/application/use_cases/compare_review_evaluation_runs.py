from dataclasses import dataclass

from agent_service.app.application.eval.interfaces.eval_repository import (
    EvalRunRepository,
)
from agent_service.app.application.eval import CompareEvaluationSummary


@dataclass(frozen=True, slots=True)
class CompareReviewEvaluationRunsResult:
    base_run_id: str
    target_run_id: str
    summary: CompareEvaluationSummary


class CompareReviewEvaluationRunsUseCase:
    def __init__(
            self,
            eval_run_repository: EvalRunRepository,
    ) -> None:
        self._eval_run_repository = eval_run_repository

    async def __call__(
            self,
            base_run_id: str,
            target_run_id: str,
    ) -> CompareReviewEvaluationRunsResult:
        base = await self._eval_run_repository.get_run(base_run_id)
        target = await self._eval_run_repository.get_run(target_run_id)
        if base is None or target is None:
            raise ValueError("One of evaluation runs not found")

        deltas = {
            "mae": target.mae - base.mae,
            "rmse": target.rmse - base.rmse,
            "feedback_jaccard_mean": target.feedback_jaccard_mean - base.feedback_jaccard_mean,
            "suggestions_f1_mean": target.suggestions_f1_mean - base.suggestions_f1_mean,
        }

        summary = CompareEvaluationSummary(
            base_run_id=base_run_id,
            target_run_id=target_run_id,
            deltas=deltas,
        )
        return CompareReviewEvaluationRunsResult(
            base_run_id=base_run_id,
            target_run_id=target_run_id,
            summary=summary,
        )
