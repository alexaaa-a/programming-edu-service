from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CriterionResult:
    id: str
    text: str
    passed: bool
    note: str = ""
    line: int | None = None


@dataclass(frozen=True, slots=True)
class ChallengeResult:
    text: str
    severity: str = "medium"
    line: int | None = None


@dataclass(frozen=True, slots=True)
class PathStepResult:
    kind: str
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TaskTestsResult:
    status: str
    total: int = 0
    passed: int = 0
    failed_names: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Review:
    score: int
    feedback: str
    suggestions: list[str] = field(default_factory=list)
    criteria: list[CriterionResult] = field(default_factory=list)
    challenges: list[ChallengeResult] = field(default_factory=list)
    agent_path: list[PathStepResult] = field(default_factory=list)
    tests: TaskTestsResult | None = None
