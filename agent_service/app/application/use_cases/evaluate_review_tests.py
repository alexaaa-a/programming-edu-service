from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from agent_service.app.application.dto import Review
from agent_service.app.application.eval.interfaces.eval_repository import (
    EvalRunRepository,
)
from agent_service.app.application.eval.interfaces.review_metrics_calculator import (
    ReviewMetricsCalculator,
)
from agent_service.app.application.eval import (
    ReviewEvaluationResult,
    ReviewEvaluationRunSummary,
    TestReviewSubmission,
)
from agent_service.app.application.use_cases.review_submission import (
    ReviewSubmissionUseCase,
)


@dataclass(frozen=True, slots=True)
class EvaluateReviewTestsResult:
    run_id: str
    summary: ReviewEvaluationRunSummary


class EvaluateReviewTestsUseCase:
    def __init__(
        self,
        *,
        review_submission_use_case: ReviewSubmissionUseCase,
        eval_run_repository: EvalRunRepository,
        metrics_calculator: ReviewMetricsCalculator,
    ) -> None:
        self._review_submission_use_case = review_submission_use_case
        self._eval_run_repository = eval_run_repository
        self._metrics_calculator = metrics_calculator

    async def __call__(
        self,
        *,
        tests: Sequence[TestReviewSubmission],
        run_id: str | None = None,
    ) -> EvaluateReviewTestsResult:
        if run_id is None:
            run_id = _make_run_id()

        results: list[ReviewEvaluationResult] = []

        score_abs_errors: list[float] = []
        score_squared_errors: list[float] = []
        feedback_jaccards: list[float] = []
        suggestions_f1s: list[float] = []

        for t in tests:
            submission_result = await self._review_submission_use_case(
                submission_id=t.submission_id,
                code=t.code,
                task_description=t.task_description,
            )
            actual_review: Review = submission_result.review

            metrics = self._metrics_calculator.compute(
                expected=t.expected_review,
                actual=actual_review,
            )

            score_abs_errors.append(metrics.score_abs_error)
            score_squared_errors.append(metrics.score_squared_error)
            feedback_jaccards.append(metrics.feedback_jaccard)
            suggestions_f1s.append(metrics.suggestions_f1)

            results.append(
                ReviewEvaluationResult(
                    submission_id=t.submission_id,
                    actual_review=actual_review,
                    expected_review=t.expected_review,
                    metrics=metrics,
                ),
            )

        mae = sum(score_abs_errors) / len(score_abs_errors) if score_abs_errors else 0.0
        rmse = (
            (sum(score_squared_errors) / len(score_squared_errors)) ** 0.5
            if score_squared_errors
            else 0.0
        )
        feedback_jaccard_mean = (
            sum(feedback_jaccards) / len(feedback_jaccards)
            if feedback_jaccards
            else 0.0
        )
        suggestions_f1_mean = (
            sum(suggestions_f1s) / len(suggestions_f1s)
            if suggestions_f1s
            else 0.0
        )

        summary = ReviewEvaluationRunSummary(
            run_id=run_id,
            created_at=_now_utc(),
            total=len(tests),
            mae=mae,
            rmse=rmse,
            feedback_jaccard_mean=feedback_jaccard_mean,
            suggestions_f1_mean=suggestions_f1_mean,
            results=results,
        )

        await self._eval_run_repository.save_run(summary)
        return EvaluateReviewTestsResult(run_id=run_id, summary=summary)


def _make_run_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)
