from abc import abstractmethod
from typing import Any, Protocol


class CacheInterface(Protocol):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def set(
        self,
        key: str,
        value: str,
        ttl_sec: int | None = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError
