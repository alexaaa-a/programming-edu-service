from datetime import datetime

from pydantic import BaseModel, Field


class TaskResponse(BaseModel):
    task_id: int
    user_id: int
    user_project_id: int
    sprint_id: int
    title: str
    description: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    close_quality: str | None = None
    close_note: str | None = None


class BoardResponse(BaseModel):
    todo: list[TaskResponse]
    in_progress: list[TaskResponse]
    review: list[TaskResponse]
    done: list[TaskResponse]


class UpdateTaskStatus(BaseModel):
    status: str


class PeerReviewIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
