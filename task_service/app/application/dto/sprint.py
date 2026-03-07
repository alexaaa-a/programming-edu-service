import datetime
from dataclasses import dataclass


@dataclass
class SprintDTO:
    sprint_id: int
    user_project_id: int
    user_id: int
    order: int
    status: str
    started_at: datetime.datetime
    completed_at: datetime.datetime | None
