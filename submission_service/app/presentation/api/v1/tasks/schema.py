import datetime
from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    id: str
    text: str
    passed: bool
    note: str = ""


class ChallengeResult(BaseModel):
    text: str
    severity: str = "medium"


class PathStepResult(BaseModel):
    kind: str
    name: str
    status: str
    detail: str = ""


class Review(BaseModel):
    score: int
    feedback: str
    suggestions: list[str]
    criteria: list[CriterionResult] = Field(default_factory=list)
    challenges: list[ChallengeResult] = Field(default_factory=list)
    agent_path: list[PathStepResult] = Field(default_factory=list)


class Submission(BaseModel):
    submission_id: int
    user_id: int
    task_id: int
    code: str
    status: str
    review: Review | None
    created_at: datetime.datetime
    reviewed_at: datetime.datetime | None
