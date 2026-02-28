from collections.abc import AsyncIterable

import redis.asyncio as redis
from dishka import provide, Provider, Scope

from user_service.app.application.interfaces.db.session_repo import SessionRepositoryInterface
from user_service.app.application.interfaces.db.cache import CacheInterface
from user_service.app.infrastructure.redis.cache import RedisCache
from user_service.app.infrastructure.redis.session_repo import RedisSessionRepository
from user_service.app.config import Settings


class RedisProvider(Provider):

    @provide(scope=Scope.APP)
    async def setup(self, settings: Settings) -> AsyncIterable[redis.Redis]:
        client = redis.Redis(
            host=settings.redis_settings.host,
            port=settings.redis_settings.port,
            db=settings.redis_settings.db,
            decode_responses=True
        )

        try:
            yield client
        finally:
            await client.close()


class RedisCacheProvider(Provider):
    cache = provide(RedisCache, provides=CacheInterface, scope=Scope.APP)
    session_db = provide(RedisSessionRepository, provides=SessionRepositoryInterface, scope=Scope.APP)
