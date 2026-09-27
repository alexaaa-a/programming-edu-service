from abc import abstractmethod
from typing import Any, Protocol


class RunCheckpointStore(Protocol):
    @abstractmethod
    async def load(self, run_key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, run_key: str, state: dict[str, Any], ttl_sec: int | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, run_key: str) -> None:
        raise NotImplementedError
