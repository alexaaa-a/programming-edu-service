from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import redis.asyncio as redis

from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces.retrieve_cache import RetrieveCache


class RedisRetrieveCache(RetrieveCache):
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> list[RetrievedDocument] | None:
        cached = await self._redis.get(key)
        if not cached:
            return None

        try:
            payload: list[dict[str, Any]] = json.loads(cached)
        except Exception:
            return None

        docs: list[RetrievedDocument] = []
        for item in payload:
            docs.append(
                RetrievedDocument(
                    text=str(item.get("text", "")),
                    metadata=item.get("metadata") or {},
                    score=item.get("score"),
                ),
            )
        return docs

    async def set(
        self,
        key: str,
        value: list[RetrievedDocument],
        *,
        ttl_sec: int,
    ) -> None:
        if ttl_sec <= 0:
            return

        payload: list[dict[str, Any]] = []
        for d in value:
            payload.append(
                {
                    "text": d.text,
                    "metadata": d.metadata,
                    "score": d.score,
                },
            )

        await self._redis.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl_sec)
