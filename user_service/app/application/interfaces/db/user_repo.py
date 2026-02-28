from abc import abstractmethod
from typing import Protocol

from user_service.app.application.dto import UserDTO


class UserRepositoryInterface(Protocol):

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> UserDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def get_user_by_email(self, email: str) -> UserDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def create_or_update_user(self, user: UserDTO) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def update_profile(
        self,
        user_id: int,
        *,
        name: str | None = None,
        surname: str | None = None,
        username: str | None = None,
        email: str | None = None,
        direction: str | None = None,
        level: str | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def update_password(self, user_id: int, new_password_hash: str) -> bool:
        raise NotImplementedError
