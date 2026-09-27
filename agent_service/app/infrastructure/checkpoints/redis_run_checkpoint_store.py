import json
import logging
from typing import Any

import redis.asyncio as redis

from agent_service.app.application.interfaces.run_checkpoint_store import RunCheckpointStore


class RedisRunCheckpointStore:
    def __init__(
            self,
            redis_client: redis.Redis,
            key_prefix: str = "agent:run:",
            default_ttl_sec: int = 86_400,
            logger: logging.Logger | None = None,
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._default_ttl_sec = max(60, int(default_ttl_sec))
        self._logger = logger

    def _key(self, run_key: str) -> str:
        return f"{self._prefix}{run_key}"

    async def load(self, run_key: str) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key(run_key))
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            if self._logger is not None:
                self._logger.warning("checkpoint.corrupt key=%s", run_key)
            return None
        return data if isinstance(data, dict) else None

    async def save(self, run_key: str, state: dict[str, Any], ttl_sec: int | None = None) -> None:
        ttl = self._default_ttl_sec if ttl_sec is None else max(60, int(ttl_sec))
        await self._redis.set(
            self._key(run_key),
            json.dumps(state, ensure_ascii=False),
            ex=ttl,
        )

    async def delete(self, run_key: str) -> None:
        await self._redis.delete(self._key(run_key))


class InMemoryRunCheckpointStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def load(self, run_key: str) -> dict[str, Any] | None:
        state = self._data.get(run_key)
        return dict(state) if state is not None else None

    async def save(self, run_key: str, state: dict[str, Any], ttl_sec: int | None = None) -> None:
        self._data[run_key] = dict(state)

    async def delete(self, run_key: str) -> None:
        self._data.pop(run_key, None)


def ensure_checkpoint_store(store: RunCheckpointStore | None) -> RunCheckpointStore:
    return store if store is not None else InMemoryRunCheckpointStore()
