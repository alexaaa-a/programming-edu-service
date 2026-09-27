import datetime
from dataclasses import dataclass, field


@dataclass
class CriterionResultDTO:
    id: str
    text: str
    passed: bool
    note: str = ""


@dataclass
class ChallengeResultDTO:
    text: str
    severity: str = "medium"


@dataclass
class PathStepResultDTO:
    kind: str
    name: str
    status: str
    detail: str = ""


@dataclass
class ReviewDTO:
    score: int
    feedback: str
    suggestions: list[str]
    criteria: list[CriterionResultDTO] = field(default_factory=list)
    challenges: list[ChallengeResultDTO] = field(default_factory=list)
    agent_path: list[PathStepResultDTO] = field(default_factory=list)


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
