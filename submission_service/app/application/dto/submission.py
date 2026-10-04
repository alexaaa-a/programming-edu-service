import datetime
from dataclasses import dataclass, field


@dataclass
class SkillShareDTO:
    skill_id: str
    share: float


@dataclass
class CriterionResultDTO:
    id: str
    text: str
    passed: bool
    note: str = ""
    skills: list[SkillShareDTO] = field(default_factory=list)
    line: int | None = None


@dataclass
class ChallengeResultDTO:
    text: str
    severity: str = "medium"
    line: int | None = None


@dataclass
class PathStepResultDTO:
    kind: str
    name: str
    status: str
    detail: str = ""


@dataclass
class TaskTestsDTO:
    status: str
    total: int = 0
    passed: int = 0
    failed_names: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class ReviewDTO:
    score: int
    feedback: str
    suggestions: list[str]
    criteria: list[CriterionResultDTO] = field(default_factory=list)
    challenges: list[ChallengeResultDTO] = field(default_factory=list)
    agent_path: list[PathStepResultDTO] = field(default_factory=list)
    tests: TaskTestsDTO | None = None


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
