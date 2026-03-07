import datetime
from dataclasses import dataclass


@dataclass
class UserProjectDTO:
    user_project_id: int
    user_id: int
    template_id: int
    status: str
    current_sprint_order: int
    created_at: datetime.datetime
    completed_at: datetime.datetime | None


@dataclass
class MetaUserDTO:
    user_id: int
    direction: str
    level: str
