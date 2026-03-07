import logging

import redis.asyncio as redis

from task_service.app.application.interfaces.db.cache import CacheInterface
from task_service.app.config import Settings


class RedisCache(CacheInterface):
    def __init__(
        self,
        redis_client: redis.Redis,
        logger: logging.Logger,
        settings: Settings,
    ) -> None:
        self.redis_client = redis_client
        self.logger = logger
        self.settings = settings
        self._default_ttl = settings.redis_settings.cache_ttl_sec

    async def get(self, key: str) -> str | None:
        try:
            data = await self.redis_client.get(key)
            if data is None:
                return None
            return data if isinstance(data, str) else data.decode("utf-8")
        except Exception:
            self.logger.exception("Redis get failed for key=%s", key)
            return None

    async def set(
        self,
        key: str,
        value: str,
        ttl_sec: int | None = None,
    ) -> bool:
        try:
            ex = ttl_sec if ttl_sec is not None else self._default_ttl
            await self.redis_client.set(key, value, ex=ex)
            return True
        except Exception:
            self.logger.exception("Redis set failed for key=%s", key)
            return False

    async def delete(self, key: str) -> bool:
        try:
            await self.redis_client.delete(key)
            return True
        except Exception:
            self.logger.exception("Redis delete failed for key=%s", key)
            return False

    async def health(self) -> bool:
        try:
            pong = await self.redis_client.ping()
            return pong is True
        except Exception:
            self.logger.exception("Redis health check failed")
            return False
