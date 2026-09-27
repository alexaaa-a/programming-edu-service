import asyncio
from datetime import datetime, timedelta, timezone

from agent_service.app.application.chat_transcript import chat_thread_id, transcript_message
from agent_service.app.infrastructure.chat_history.mongo_chat_history_repository import (
    MongoChatHistoryRepository,
)


class _Cursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = list(docs)
        self._index = 0

    def sort(self, spec: list[tuple[str, int]]) -> "_Cursor":
        def key(doc: dict) -> tuple:
            return tuple(doc.get(field) for field, _direction in spec)

        self._docs.sort(key=key)
        return self

    def __aiter__(self) -> "_Cursor":
        self._index = 0
        return self

    async def __anext__(self) -> dict:
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._index]
        self._index += 1
        return item


class _Collection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find(self, query: dict) -> _Cursor:
        thread_id = query.get("thread_id")
        return _Cursor([doc for doc in self.docs if doc.get("thread_id") == thread_id])

    async def insert_one(self, doc: dict) -> None:
        stored = dict(doc)
        stored["_id"] = len(self.docs) + 1
        self.docs.append(stored)

    async def find_one(self, query: dict, sort: list[tuple[str, int]] | None = None) -> dict | None:
        found = [
            doc
            for doc in self.docs
            if all(doc.get(key) == value for key, value in query.items())
        ]
        if sort:
            field, direction = sort[0]
            found.sort(key=lambda doc: doc.get(field), reverse=direction < 0)
        return found[0] if found else None

    async def delete_one(self, query: dict) -> None:
        self.docs = [doc for doc in self.docs if doc.get("_id") != query.get("_id")]

    async def delete_many(self, query: dict) -> None:
        self.docs = [doc for doc in self.docs if doc.get("thread_id") != query.get("thread_id")]


def test_thread_is_shared_across_devices_and_split_by_task():
    assert chat_thread_id("7", "phone") == chat_thread_id("7", "laptop")
    assert chat_thread_id("7", "phone") == "u7:general"
    assert chat_thread_id("7", "phone", task_id=4) == "u7:task:4"
    assert chat_thread_id("8", "phone") != chat_thread_id("7", "phone")
    assert chat_thread_id(None, "legacy") == "legacy"


def test_transcript_keeps_speaker_and_full_text():
    shown = transcript_message(
        {
            "role": "assistant",
            "content": "[Эмма (Тестировщик)] Смотри на пустой список.",
            "turn_id": "t1",
            "timestamp": "2026-09-26T12:00:00+00:00",
        }
    )
    assert shown["text"] == "Смотри на пустой список."
    assert shown["sender"] == "Эмма (Тестировщик)"
    assert shown["id"] == "t1:assistant"


def test_mongo_history_keeps_every_message_and_limits_only_the_model_tail():
    repo = MongoChatHistoryRepository(_Collection(), max_messages=2)

    async def _run() -> None:
        start = datetime(2026, 9, 26, tzinfo=timezone.utc)
        for index in range(3):
            await repo.append_message("u7:general", "user", f"m{index}", turn_id=f"t{index}")
            repo._coll.docs[-1]["timestamp"] = start + timedelta(seconds=index)

        full = await repo.list_history("u7:general")
        tail = await repo.get_history("u7:general")
        other = await repo.list_history("u8:general")
        assert [row["content"] for row in full] == ["m0", "m1", "m2"]
        assert [row["content"] for row in tail] == ["m1", "m2"]
        assert other == []

    asyncio.run(_run())
