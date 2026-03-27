from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, status

from agent_service.app.application.dto import Review
from agent_service.app.application.eval.models import TestReviewSubmission
from agent_service.app.application.use_cases import (
    CompareReviewEvaluationRunsUseCase,
    EvaluateReviewTestsUseCase,
)
from agent_service.app.presentation.api.v1.eval.schema import (
    CompareReviewEvaluationRunsRequest,
    CompareReviewEvaluationRunsResponse,
    EvaluateReviewTestsRequest,
    EvaluateReviewTestsResponse,
    ReviewEvaluationSummarySchema,
)


router = APIRouter(route_class=DishkaRoute)


def _summary_to_response(summary) -> ReviewEvaluationSummarySchema:  # type: ignore[no-untyped-def]
    return ReviewEvaluationSummarySchema(
        total=summary.total,
        mae=summary.mae,
        rmse=summary.rmse,
        feedback_jaccard_mean=summary.feedback_jaccard_mean,
        suggestions_f1_mean=summary.suggestions_f1_mean,
    )


@router.post(
    "/eval/review-tests",
    status_code=status.HTTP_200_OK,
    response_model=EvaluateReviewTestsResponse,
    description="Прогон тестовых сабмишнов и сохранение eval run",
)
async def evaluate_review_tests(
    body: EvaluateReviewTestsRequest,
    uc: FromDishka[EvaluateReviewTestsUseCase],
) -> EvaluateReviewTestsResponse:
    tests = [
        TestReviewSubmission(
            submission_id=t.submission_id,
            code=t.code,
            task_description=t.task_description,
            expected_review=Review(
                score=t.expected_review.score,
                feedback=t.expected_review.feedback,
                suggestions=t.expected_review.suggestions,
            ),
        )
        for t in body.tests
    ]

    result = await uc(tests=tests, run_id=body.run_id)

    return EvaluateReviewTestsResponse(
        run_id=result.run_id,
        summary=_summary_to_response(result.summary),
    )


@router.post(
    "/eval/compare",
    status_code=status.HTTP_200_OK,
    response_model=CompareReviewEvaluationRunsResponse,
    description="Сравнение двух eval run по ML метрикам",
)
async def compare_review_evaluation_runs(
    body: CompareReviewEvaluationRunsRequest,
    uc: FromDishka[CompareReviewEvaluationRunsUseCase],
) -> CompareReviewEvaluationRunsResponse:
    result = await uc(base_run_id=body.base_run_id, target_run_id=body.target_run_id)
    return CompareReviewEvaluationRunsResponse(
        base_run_id=result.base_run_id,
        target_run_id=result.target_run_id,
        deltas=result.summary.deltas,
    )
