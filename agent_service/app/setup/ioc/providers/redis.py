from __future__ import annotations

from collections.abc import AsyncIterable

import redis.asyncio as redis
from dishka import Provider, Scope, provide

from agent_service.app.application.interfaces.retrieve_cache import RetrieveCache
from agent_service.app.config import Settings
from agent_service.app.infrastructure.memory.redis_retrieve_cache import RedisRetrieveCache


class RedisClientProvider(Provider):
    @provide(scope=Scope.APP)
    async def redis_client(self, settings: Settings) -> AsyncIterable[redis.Redis]:
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


class RedisRetrieveCacheProvider(Provider):
    @provide(scope=Scope.APP, provides=RetrieveCache)
    def retrieve_cache(self, redis_client: redis.Redis) -> RetrieveCache:
        return RedisRetrieveCache(redis_client=redis_client)


RedisProviders = [
    RedisClientProvider(),
    RedisRetrieveCacheProvider(),
]

