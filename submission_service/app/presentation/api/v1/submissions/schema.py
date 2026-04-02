import datetime
from pydantic import BaseModel


class Review(BaseModel):
    score: int
    feedback: str
    suggestions: list[str]


class Submission(BaseModel):
    submission_id: int
    user_id: int
    task_id: int
    code: str
    status: str
    review: Review | None
    created_at: datetime.datetime
    reviewed_at: datetime.datetime | None


class Submit(BaseModel):
    code: str
    task_id: int


class UserSubmissionStats(BaseModel):
    total_submissions: int
    reviewed_submissions: int
    pending_submissions: int
    failed_submissions: int
    average_score: float | None
    best_score: int | None
    tasks_attempted: int
