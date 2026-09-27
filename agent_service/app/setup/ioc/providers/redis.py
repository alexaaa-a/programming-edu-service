from collections.abc import AsyncIterable
import logging

import redis.asyncio as redis
from dishka import Provider, Scope, provide

from agent_service.app.application.interfaces.retrieve_cache import RetrieveCache
from agent_service.app.application.interfaces.run_checkpoint_store import RunCheckpointStore
from agent_service.app.config import Settings
from agent_service.app.infrastructure.checkpoints.redis_run_checkpoint_store import (
    RedisRunCheckpointStore,
)
from agent_service.app.infrastructure.memory.redis_retrieve_cache import RedisRetrieveCache


class RedisClientProvider(Provider):
    @provide(scope=Scope.APP)
    async def redis_client(self, settings: Settings) -> AsyncIterable[redis.Redis]:
        client = redis.Redis(
            host=settings.redis_settings.host,
            port=settings.redis_settings.port,
            db=settings.redis_settings.db,
            password=settings.redis_settings.password,
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


class RunCheckpointStoreProvider(Provider):
    @provide(scope=Scope.APP, provides=RunCheckpointStore)
    def run_checkpoint_store(
            self,
            redis_client: redis.Redis,
            settings: Settings,
            logger: logging.Logger,
    ) -> RunCheckpointStore:
        return RedisRunCheckpointStore(
            redis_client,
            default_ttl_sec=settings.redis_settings.checkpoint_ttl_sec,
            logger=logger,
        )


RedisProviders = [
    RedisClientProvider(),
    RedisRetrieveCacheProvider(),
    RunCheckpointStoreProvider(),
]

