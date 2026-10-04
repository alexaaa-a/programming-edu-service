from dataclasses import dataclass
from datetime import datetime


DRILL_WEIGHT = 0.5


@dataclass(frozen=True, slots=True)
class Drill:
    id: str
    skill_id: str
    title: str
    prompt: str
    starter: str
    tests: str
    reference: str
    minutes: int = 5


@dataclass(frozen=True, slots=True)
class DrillRun:
    drill_id: str
    skill_id: str
    passed: int
    total: int
    at: datetime

    @property
    def ok(self) -> bool:
        return self.total > 0 and self.passed >= self.total

    @property
    def outcome(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.passed / self.total))


@dataclass(frozen=True, slots=True)
class DrillPick:
    drill: Drill
    skill_id: str
    skill_title: str
    kind: str
    reason: str
    days_since: int = 0
    retention: float = 1.0
