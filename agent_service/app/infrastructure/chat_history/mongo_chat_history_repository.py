from datetime import datetime, timezone
from typing import Any

from agent_service.app.application.interfaces import ChatHistoryRepository


class MongoChatHistoryRepository(ChatHistoryRepository):
    def __init__(self, collection: Any, max_messages: int = 20) -> None:
        self._coll = collection
        self._max_messages = max(1, int(max_messages))

    async def get_history(self, session_id: str) -> list[Any]:
        docs = await self._load(session_id)
        if len(docs) > self._max_messages:
            docs = docs[-self._max_messages:]
        return docs

    async def list_history(self, session_id: str) -> list[Any]:
        return await self._load(session_id)

    async def append_message(
            self,
            session_id: str,
            role: str,
            content: str,
            turn_id: str | None = None,
    ) -> None:
        await self._coll.insert_one(
            {
                "thread_id": session_id,
                "role": role,
                "content": content,
                "turn_id": turn_id or "",
                "timestamp": datetime.now(tz=timezone.utc),
                "order": 0 if role == "user" else 1,
            }
        )

    async def rollback_last_message(
            self,
            session_id: str,
            role: str,
            content: str,
    ) -> None:
        doc = await self._coll.find_one(
            {"thread_id": session_id, "role": role, "content": content},
            sort=[("timestamp", -1)],
        )
        if doc is not None:
            await self._coll.delete_one({"_id": doc["_id"]})

    async def clear_history(self, session_id: str) -> None:
        await self._coll.delete_many({"thread_id": session_id})

    async def _load(self, session_id: str) -> list[dict[str, Any]]:
        cursor = self._coll.find({"thread_id": session_id}).sort(
            [("timestamp", 1), ("order", 1)]
        )
        docs: list[dict[str, Any]] = []
        async for doc in cursor:
            created = doc.get("timestamp")
            if isinstance(created, datetime):
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                created = created.isoformat()
            docs.append(
                {
                    "role": doc.get("role"),
                    "content": doc.get("content"),
                    "timestamp": created,
                    "turn_id": doc.get("turn_id") or "",
                }
            )
        return docs
