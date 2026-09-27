from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CriterionResult:
    id: str
    text: str
    passed: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class ChallengeResult:
    text: str
    severity: str = "medium"


@dataclass(frozen=True, slots=True)
class PathStepResult:
    kind: str
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Review:
    score: int
    feedback: str
    suggestions: list[str] = field(default_factory=list)
    criteria: list[CriterionResult] = field(default_factory=list)
    challenges: list[ChallengeResult] = field(default_factory=list)
    agent_path: list[PathStepResult] = field(default_factory=list)
