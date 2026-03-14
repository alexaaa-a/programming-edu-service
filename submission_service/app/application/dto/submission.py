import datetime
from dataclasses import dataclass

@dataclass
class ReviewDTO:
    score: int
    feedback: str
    suggestions: list[str]


@dataclass
class SubmissionDTO:
    submission_id: int
    user_id: int
    task_id: int
    code: str
    status: str
    review: ReviewDTO | None
    created_at: datetime.datetime
    reviewed_at: datetime.datetime | None
