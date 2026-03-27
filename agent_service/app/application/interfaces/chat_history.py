from typing import Any, Protocol


class ChatHistoryRepository(Protocol):
    async def get_history(self, session_id: str) -> list[Any]:
        raise NotImplementedError

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        raise NotImplementedError

    async def clear_history(self, session_id: str) -> None:
        raise NotImplementedError
