from pydantic import BaseModel, Field


class ReviewSchema(BaseModel):
    score: int = Field(..., ge=1, le=10)
    feedback: str
    suggestions: list[str] = Field(default_factory=list)


class TestReviewSubmissionSchema(BaseModel):
    submission_id: str
    code: str
    task_description: str
    expected_review: ReviewSchema


class EvaluateReviewTestsRequest(BaseModel):
    tests: list[TestReviewSubmissionSchema]
    run_id: str | None = None


class ReviewEvaluationSummarySchema(BaseModel):
    total: int
    mae: float
    rmse: float
    feedback_jaccard_mean: float
    suggestions_f1_mean: float


class EvaluateReviewTestsResponse(BaseModel):
    run_id: str
    summary: ReviewEvaluationSummarySchema


class CompareReviewEvaluationRunsRequest(BaseModel):
    base_run_id: str
    target_run_id: str


class CompareReviewEvaluationRunsResponse(BaseModel):
    base_run_id: str
    target_run_id: str
    deltas: dict[str, float]
