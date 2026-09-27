from abc import abstractmethod
from typing import Protocol


class SessionRepositoryInterface(Protocol):
    @abstractmethod
    async def save_refresh_token(self, refresh_token: str, user_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def get_refresh_token(self, user_id: int) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def delete_refresh_token(self, user_id: int) -> bool:
        raise NotImplementedError
