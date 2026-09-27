import datetime
from abc import abstractmethod
from typing import Protocol

from task_service.app.application.dto.task import TaskDTO


class TaskDBInterface(Protocol):

    @abstractmethod
    async def create_task(self, task: TaskDTO) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_tasks(self, sprint_id: int, user_id: int) -> list[TaskDTO] | None:
        raise NotImplementedError

    @abstractmethod
    async def update_task(
            self,
            task_id: int,
            new_status: str,
            completed_at: datetime.datetime | None = None,
            close_quality: str | None = None,
            user_id: int | None = None,
            close_note: str | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_task_by_id(self, task_id: int, user_id: int) -> TaskDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def get_task_by_task_id(self, task_id: int) -> TaskDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_tasks_by_sprint(self, sprint_id: int, user_id: int) -> bool:
        raise NotImplementedError
