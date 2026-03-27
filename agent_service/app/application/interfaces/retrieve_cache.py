from __future__ import annotations

from abc import abstractmethod
from typing import Protocol

from agent_service.app.application.dto.rag import RetrievedDocument


class RetrieveCache(Protocol):
    @abstractmethod
    async def get(self, key: str) -> list[RetrievedDocument] | None:
        raise NotImplementedError

    @abstractmethod
    async def set(
        self,
        key: str,
        value: list[RetrievedDocument],
        *,
        ttl_sec: int,
    ) -> None:
        raise NotImplementedError

