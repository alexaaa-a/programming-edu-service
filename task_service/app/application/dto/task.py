import datetime
from dataclasses import dataclass


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
