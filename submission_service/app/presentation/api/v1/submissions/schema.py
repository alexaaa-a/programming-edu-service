import datetime
from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    id: str
    text: str
    passed: bool
    note: str = ""
    line: int | None = None


class ChallengeResult(BaseModel):
    text: str
    severity: str = "medium"
    line: int | None = None


class PathStepResult(BaseModel):
    kind: str
    name: str
    status: str
    detail: str = ""


class TaskTests(BaseModel):
    status: str
    total: int = 0
    passed: int = 0
    failed_names: list[str] = Field(default_factory=list)
    detail: str = ""


class Review(BaseModel):
    score: int
    feedback: str
    suggestions: list[str]
    criteria: list[CriterionResult] = Field(default_factory=list)
    challenges: list[ChallengeResult] = Field(default_factory=list)
    agent_path: list[PathStepResult] = Field(default_factory=list)
    tests: TaskTests | None = None


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


class TrajectorySkill(BaseModel):
    id: str
    title: str
    status: str
    mastery: float
    predicted_success: float
    retention: float
    evidence: float
    opportunities: int
    last_practiced_at: datetime.datetime | None = None


class TrajectoryFocus(BaseModel):
    skill_id: str
    title: str
    summary: str
    kind: str
    status: str
    mastery: float
    predicted_success: float
    why: str
    steps: list[str] = Field(default_factory=list)
    mentor: str
    mentor_name: str
    ask: str
    evidence: list[str] = Field(default_factory=list)


class TrajectoryRecommendation(BaseModel):
    kind: str
    title: str
    detail: str
    skill_id: str | None = None
    task_id: int | None = None
    mentor: str | None = None
    ask: str | None = None


class TrajectoryNudge(BaseModel):
    kind: str
    task_id: int
    hours_since: int = 0
    score: int | None = None
    detail: str = ""


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
    velocity: float = 0.0
    readiness_threshold: float = 0.0
    skills: list[TrajectorySkill] = Field(default_factory=list)
    focus: TrajectoryFocus | None = None
    recommendations: list[TrajectoryRecommendation] = Field(default_factory=list)
    next_task_id: int | None = None
    nudge: TrajectoryNudge | None = None
    model: str = ""


class DrillOffer(BaseModel):
    drill_id: str
    title: str
    prompt: str
    starter: str
    minutes: int
    skill_id: str
    skill_title: str
    kind: str
    reason: str
    days_since: int = 0
    retention: float = 1.0
