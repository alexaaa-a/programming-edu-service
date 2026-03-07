from datetime import datetime

from pydantic import BaseModel


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


class BoardResponse(BaseModel):
    todo: list[TaskResponse]
    in_progress: list[TaskResponse]
    review: list[TaskResponse]
    done: list[TaskResponse]


class UpdateTaskStatus(BaseModel):
    status: str
