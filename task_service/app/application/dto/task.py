import datetime
from dataclasses import dataclass, fields


@dataclass
class TaskDTO:
    task_id: int
    user_id: int
    user_project_id: int
    sprint_id: int
    title: str
    description: str
    status: str
    created_at: datetime.datetime
    completed_at: datetime.datetime | None
    close_quality: str | None = None
    review_bug: str | None = None
    close_note: str | None = None

    @classmethod
    def from_document(cls, doc: dict) -> "TaskDTO":
        data = dict(doc)
        data.pop("_id", None)
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in allowed})
