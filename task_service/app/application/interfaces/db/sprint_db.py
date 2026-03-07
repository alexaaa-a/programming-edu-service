import datetime
from abc import abstractmethod
from typing import Protocol

from task_service.app.application.dto.sprint import SprintDTO


class SprintDBInterface(Protocol):

    @abstractmethod
    async def create_sprint(self, sprint: SprintDTO) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_current_sprint(
            self,
            user_id: int
    ) -> SprintDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def update_sprint(
            self,
            user_id: int,
            old_status: str,
            new_status: str,
            completed_at: datetime.datetime | None = None
    ) -> bool:
        raise NotImplementedError
