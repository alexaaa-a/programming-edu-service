from typing import Any, Protocol


class ChatHistoryRepository(Protocol):
    async def get_history(self, session_id: str) -> list[Any]:
        raise NotImplementedError

    async def list_history(self, session_id: str) -> list[Any]:
        raise NotImplementedError

    async def append_message(
            self,
            session_id: str,
            role: str,
            content: str,
            turn_id: str | None = None,
    ) -> None:
        raise NotImplementedError

    async def rollback_last_message(
            self,
            session_id: str,
            role: str,
            content: str,
    ) -> None:
        return None

    async def clear_history(self, session_id: str) -> None:
        raise NotImplementedError
