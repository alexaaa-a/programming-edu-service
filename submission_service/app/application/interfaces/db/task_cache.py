from abc import abstractmethod
from typing import Protocol


class TaskCacheInterface(Protocol):

    @abstractmethod
    async def upsert_task(
        self,
        task_id: int,
        user_id: int,
        status: str,
        task_description: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_status(self, task_id: int, user_id: int) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def get_task_description(self, task_id: int, user_id: int) -> str | None:
        raise NotImplementedError
