import logging

import redis.asyncio as redis


class RedisRunGuard:
    def __init__(
            self,
            client: redis.Redis,
            ttl_sec: int = 30,
            logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._ttl = ttl_sec
        self._logger = logger or logging.getLogger("agent_service.run_guard")

    def _key(self, user_id: str) -> str:
        return f"run_tests:lock:{user_id}"

    async def acquire(self, user_id: str) -> bool:
        try:
            return bool(await self._client.set(self._key(user_id), "1", ex=self._ttl, nx=True))
        except Exception:
            self._logger.exception("run_guard.acquire_failed")
            return True

    async def release(self, user_id: str) -> None:
        try:
            await self._client.delete(self._key(user_id))
        except Exception:
            self._logger.exception("run_guard.release_failed")


class RedisNudgeMemory:
    def __init__(
            self,
            client: redis.Redis,
            logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        self._logger = logger or logging.getLogger("agent_service.nudge")

    async def remember(self, key: str, ttl_sec: int) -> bool:
        try:
            return bool(await self._client.set(key, "1", ex=ttl_sec, nx=True))
        except Exception:
            self._logger.exception("nudge.remember_failed")
            return True
