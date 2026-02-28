import redis.asyncio as redis
import logging

from user_service.app.application.interfaces.db.cache import CacheInterface


class RedisCache(CacheInterface):
    def __init__(self, redis_client: redis.Redis, logger: logging.Logger) -> None:
        self.redis_client = redis_client
        self.logger = logger

    async def health(self) -> bool:
        try:
            pong = await self.redis_client.ping()
            return pong is True

        except Exception:
            self.logger.exception("Exception when connecting to Redis")
            return False
