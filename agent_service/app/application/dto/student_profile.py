from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StudentProfile:
    user_id: str
    facts: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
    last_task_id: str | None = None
    reviews_count: int = 0
