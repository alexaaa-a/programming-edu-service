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
