from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from motor.motor_asyncio import AsyncIOMotorClient

from user_service.app.config import Settings
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.interfaces.db.mongo_db import MongoDBInterface
from user_service.app.infrastructure.mongo.gateway import MongoGateway
from user_service.app.infrastructure.mongo.user_repo import UserRepository


class MongoClientProvider(Provider):

    @provide(scope=Scope.APP)
    async def mongo_client(self, settings: Settings) -> AsyncIterable[AsyncIOMotorClient]:
        client = AsyncIOMotorClient(
            str(settings.mongo_settings.connection_string),
            maxIdleTimeMS=settings.mongo_settings.server_selection_timeout_ms,
        )
        try:
            yield client
        finally:
            client.close()


class MongoDBProvider(Provider):
    user_db = provide(UserRepository, provides=UserRepositoryInterface, scope=Scope.APP)
    mongo_db = provide(MongoGateway, provides=MongoDBInterface, scope=Scope.APP)
