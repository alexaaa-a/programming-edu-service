from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ASCENDING

from agent_service.app.application.interfaces import ChatHistoryRepository


@dataclass(frozen=True, slots=True)
class MongoChatHistoryConfig:
    collection_name: str = "chat_history"
    session_id_field: str = "session_id"
    role_field: str = "role"
    content_field: str = "content"
    timestamp_field: str = "timestamp"

    session_id_index_name: str = "idx_chat_history_session_id"
    session_id_timestamp_index_name: str = "idx_chat_history_session_id_ts"
    max_messages: int = 20


class MongoChatHistoryRepository(ChatHistoryRepository):
    def __init__(
        self,
        *,
        mongo_client: AsyncIOMotorClient,
        db_name: str,
        config: MongoChatHistoryConfig | None = None,
    ) -> None:
        self._client = mongo_client
        self._db_name = db_name
        self._config = config or MongoChatHistoryConfig()

        self._collection: AsyncIOMotorCollection = self._client[self._db_name][
            self._config.collection_name
        ]

        self._indexes_ready = False
        self._indexes_lock = asyncio.Lock()

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return

        async with self._indexes_lock:
            if self._indexes_ready:
                return

            await self._collection.create_index(
                [(self._config.session_id_field, ASCENDING)],
                name=self._config.session_id_index_name,
            )
            await self._collection.create_index(
                [
                    (self._config.session_id_field, ASCENDING),
                    (self._config.timestamp_field, ASCENDING),
                ],
                name=self._config.session_id_timestamp_index_name,
            )
            self._indexes_ready = True

    async def get_history(self, session_id: str) -> list[Any]:
        await self._ensure_indexes()

        cursor = self._collection.find({self._config.session_id_field: session_id})
        max_messages = self._config.max_messages
        if max_messages is not None and max_messages > 0:
            cursor = cursor.sort(self._config.timestamp_field, -1).limit(int(max_messages))
        else:
            cursor = cursor.sort(self._config.timestamp_field, 1)

        docs: list[dict[str, Any]] = []
        async for doc in cursor:
            docs.append(doc)

        if max_messages is not None and max_messages > 0:
            docs.reverse()

        result: list[dict[str, Any]] = []
        for d in docs:
            result.append(
                {
                    "role": d.get(self._config.role_field),
                    "content": d.get(self._config.content_field),
                    "timestamp": d.get(self._config.timestamp_field),
                },
            )
        return result

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        await self._ensure_indexes()

        now = datetime.now(tz=timezone.utc)
        await self._collection.insert_one(
            {
                self._config.session_id_field: session_id,
                self._config.role_field: role,
                self._config.content_field: content,
                self._config.timestamp_field: now,
            },
        )

    async def clear_history(self, session_id: str) -> None:
        await self._ensure_indexes()
        await self._collection.delete_many({self._config.session_id_field: session_id})
