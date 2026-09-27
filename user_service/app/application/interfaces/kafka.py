from abc import abstractmethod
from typing import Protocol


class UserEventProducerInterface(Protocol):
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
    async def produce_user_registered(
            self,
            user_id: int,
            direction: str | None = None,
            level: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def produce_user_profile_updated(
            self,
            user_id: int,
            direction: str | None = None,
            level: str | None = None,
    ) -> None:
        raise NotImplementedError
