import datetime
from dataclasses import dataclass, fields


@dataclass
class SprintDTO:
    sprint_id: int
    user_project_id: int
    user_id: int
    order: int
    status: str
    started_at: datetime.datetime
    completed_at: datetime.datetime | None
    close_mode: str | None = None

    @classmethod
    def from_document(cls, doc: dict) -> "SprintDTO":
        data = dict(doc)
        data.pop("_id", None)
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in allowed})
