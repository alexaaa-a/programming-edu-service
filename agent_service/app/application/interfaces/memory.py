from abc import abstractmethod
from typing import Any, Mapping, Protocol

from agent_service.app.application.dto.rag import RetrievedDocument


class MemoryInterface(Protocol):
    @abstractmethod
    async def retrieve(
            self,
            query: str,
            k: int,
            types: set[str] | None = None,
            scope: Mapping[str, str] | None = None,
    ) -> list[RetrievedDocument]:
        raise NotImplementedError

    @abstractmethod
    async def save_document(self, text: str, metadata: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_chat_history(self, session_id: str) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    async def append_chat_message(
            self,
            session_id: str,
            role: str,
            content: str,
            turn_id: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def rollback_last_chat_message(
            self,
            session_id: str,
            role: str,
            content: str,
    ) -> None:
        return None

    async def reinforce(self, documents: list[RetrievedDocument]) -> int:
        return 0
