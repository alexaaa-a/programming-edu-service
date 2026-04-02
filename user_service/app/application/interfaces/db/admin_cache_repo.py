from abc import abstractmethod
from typing import Protocol

from user_service.app.application.dto import AdminDTO


class AdminCacheRepositoryInterface(Protocol):
    @abstractmethod
    async def get_all_admins(self) -> list[AdminDTO] | None:
        raise NotImplementedError

    @abstractmethod
    async def set_all_admins(self, admins: list[AdminDTO]) -> bool:
        raise NotImplementedError
