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


class UserTrajectory(BaseModel):
    mastery: float
    difficulty: float
    pace: float
    readiness: float
    action: str
    reason: str
    block_close: bool
    block_next_sprint: bool
    window_tasks: int
    reviewed_in_window: int
    current_task_id: int | None = None
    current_attempts: int = 0
    current_score: int | None = None
    failed_criteria: list[str] = Field(default_factory=list)
