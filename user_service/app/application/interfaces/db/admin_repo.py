from abc import abstractmethod
from typing import Protocol

from user_service.app.application.dto import AdminDTO


class AdminRepositoryInterface(Protocol):
    @abstractmethod
    async def get_role(self, user_id: int) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def set_admin(self, user_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete_admin(self, user_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_all_admins(self) -> list[AdminDTO]:
        raise NotImplementedError
