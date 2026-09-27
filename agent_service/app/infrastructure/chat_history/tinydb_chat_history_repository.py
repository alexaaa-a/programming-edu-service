import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB

from agent_service.app.application.interfaces import ChatHistoryRepository


@dataclass(frozen=True, slots=True)
class TinyDbChatHistoryConfig:
    table_name: str = "chat_history"
    max_messages: int = 20


class TinyDbChatHistoryRepository(ChatHistoryRepository):
    def __init__(
            self,
            db_path: str,
            config: TinyDbChatHistoryConfig | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._config = config or TinyDbChatHistoryConfig()
        self._lock = asyncio.Lock()
        self._db: TinyDB | None = None

    async def _ensure_db(self) -> TinyDB:
        if self._db is not None:
            return self._db
        async with self._lock:
            if self._db is not None:
                return self._db
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = TinyDB(self._db_path)
            return self._db

    async def get_history(self, session_id: str) -> list[Any]:
        db = await self._ensure_db()
        q = Query()

        def _read() -> list[dict[str, Any]]:
            table = db.table(self._config.table_name)
            docs = table.search(q.session_id == session_id)
            docs.sort(key=lambda d: d.get("timestamp", ""))
            max_messages = self._config.max_messages
            if max_messages and max_messages > 0:
                docs = docs[-max_messages:]
            return docs

        async with self._lock:
            docs = await asyncio.to_thread(_read)
        return _rows(docs)

    async def list_history(self, session_id: str) -> list[Any]:
        db = await self._ensure_db()
        q = Query()

        def _read() -> list[dict[str, Any]]:
            table = db.table(self._config.table_name)
            docs = table.search(q.session_id == session_id)
            docs.sort(key=lambda d: d.get("timestamp", ""))
            return docs

        async with self._lock:
            docs = await asyncio.to_thread(_read)
        return _rows(docs)

    async def append_message(
            self,
            session_id: str,
            role: str,
            content: str,
            turn_id: str | None = None,
    ) -> None:
        db = await self._ensure_db()
        now = datetime.now(tz=timezone.utc).isoformat()
        max_messages = self._config.max_messages

        def _write() -> None:
            table = db.table(self._config.table_name)
            doc: dict[str, Any] = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": now,
            }
            if turn_id:
                doc["turn_id"] = turn_id
            table.insert(doc)
            if max_messages and max_messages > 0:
                q = Query()
                docs = table.search(q.session_id == session_id)
                docs.sort(key=lambda d: d.get("timestamp", ""))
                overflow = len(docs) - max_messages
                if overflow > 0:
                    for doc in docs[:overflow]:
                        table.remove(doc_ids=[doc.doc_id])

        async with self._lock:
            await asyncio.to_thread(_write)

    async def rollback_last_message(
            self,
            session_id: str,
            role: str,
            content: str,
    ) -> None:
        db = await self._ensure_db()
        q = Query()

        def _rollback() -> None:
            table = db.table(self._config.table_name)
            docs = table.search(q.session_id == session_id)
            docs.sort(key=lambda d: d.get("timestamp", ""))
            for doc in reversed(docs):
                if doc.get("role") == role and doc.get("content") == content:
                    table.remove(doc_ids=[doc.doc_id])
                    return

        async with self._lock:
            await asyncio.to_thread(_rollback)

    async def clear_history(self, session_id: str) -> None:
        db = await self._ensure_db()
        q = Query()

        def _clear() -> None:
            table = db.table(self._config.table_name)
            table.remove(q.session_id == session_id)

        async with self._lock:
            await asyncio.to_thread(_clear)


def _rows(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": d.get("role"),
            "content": d.get("content"),
            "timestamp": d.get("timestamp"),
            "turn_id": d.get("turn_id"),
        }
        for d in docs
    ]
