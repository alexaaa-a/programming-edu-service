from collections.abc import AsyncIterable

import redis.asyncio as redis
from dishka import provide, Provider, Scope

from task_service.app.application.interfaces.db.cache import CacheInterface
from task_service.app.config import Settings
from task_service.app.infrastructure.redis.cache import RedisCache


class RedisProvider(Provider):
    @provide(scope=Scope.APP)
    async def setup(self, settings: Settings) -> AsyncIterable[redis.Redis]:
        client = redis.Redis(
            host=settings.redis_settings.host,
            port=settings.redis_settings.port,
            db=settings.redis_settings.db,
            decode_responses=True,
        )
        try:
            yield client
        finally:
            await client.close()


class RedisCacheProvider(Provider):
    cache = provide(RedisCache, provides=CacheInterface, scope=Scope.APP)
