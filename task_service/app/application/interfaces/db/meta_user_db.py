from abc import abstractmethod
from typing import Protocol

from task_service.app.application.dto.user import MetaUserDTO


class MetaUserDBInterface(Protocol):
    @abstractmethod
    async def create_update_meta_user(self, user: MetaUserDTO) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_meta_user(self, user_id: int) -> MetaUserDTO | None:
        raise NotImplementedError
