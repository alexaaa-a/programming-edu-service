import datetime
from abc import abstractmethod
from typing import Protocol

from task_service.app.application.dto.user import UserProjectDTO


class UserProjectDBInterface(Protocol):

    @abstractmethod
    async def get_active_user_project(self, user_id: int) -> UserProjectDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def get_user_id_by_user_project_id(
            self,
            user_project_id: int
    ) -> int | None:
        raise NotImplementedError

    @abstractmethod
    async def create_user_project(self, user_project: UserProjectDTO) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_all_user_projects(self, user_id: int) -> list[UserProjectDTO] | None:
        raise NotImplementedError

    @abstractmethod
    async def update_user_project(
            self,
            user_project_id: int,
            new_status: str,
            completed_at: datetime.datetime
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def update_current_sprint_order(
            self,
            user_project_id: int,
            new_sprint_order: int
    ) -> bool:
        raise NotImplementedError
