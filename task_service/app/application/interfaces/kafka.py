from abc import abstractmethod
from typing import Protocol


class TaskEventProducerInterface(Protocol):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def produce_task_created(
            self,
            task_id: int,
            user_id: int,
            status: str,
            task_description: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def produce_task_status_updated(
            self,
            task_id: int,
            user_id: int,
            status: str,
            task_description: str,
            round_limit: int | None = None,
    ) -> None:
        raise NotImplementedError
