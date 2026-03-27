from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent_service.app.application.dto import Review


@dataclass(frozen=True, slots=True)
class TestReviewSubmission:
    submission_id: str
    code: str
    task_description: str
    expected_review: Review


@dataclass(frozen=True, slots=True)
class ReviewEvaluationMetrics:
    score_abs_error: float
    score_squared_error: float
    feedback_jaccard: float
    suggestions_precision: float
    suggestions_recall: float
    suggestions_f1: float


@dataclass(frozen=True, slots=True)
class ReviewEvaluationResult:
    submission_id: str
    actual_review: Review
    expected_review: Review
    metrics: ReviewEvaluationMetrics


@dataclass(frozen=True, slots=True)
class ReviewEvaluationRunSummary:
    run_id: str
    created_at: datetime
    total: int
    mae: float
    rmse: float
    feedback_jaccard_mean: float
    suggestions_f1_mean: float
    results: list[ReviewEvaluationResult]


@dataclass(frozen=True, slots=True)
class CompareEvaluationSummary:
    base_run_id: str
    target_run_id: str
    deltas: dict[str, Any]
