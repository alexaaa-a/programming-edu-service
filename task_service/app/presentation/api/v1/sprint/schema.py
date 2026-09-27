import datetime
from pydantic import BaseModel


class Sprint(BaseModel):
    sprint_id: int
    user_project_id: int
    user_id: int
    order: int
    status: str
    started_at: datetime.datetime
    completed_at: datetime.datetime | None
    close_mode: str | None = None
