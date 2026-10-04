from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from motor.motor_asyncio import AsyncIOMotorClient

from submission_service.app.config import Settings
from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.interfaces.db.drills_db import DrillsDBInterface
from submission_service.app.application.interfaces.db.mongo_db import MongoDBInterface
from submission_service.app.infrastructure.mongo.gateway import MongoGateway
from submission_service.app.infrastructure.mongo.drills_db import DrillsDB
from submission_service.app.infrastructure.mongo.submissions_db import SubmissionsDB
from submission_service.app.infrastructure.mongo.task_cache_db import TaskCacheDB


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
    mongo_db = provide(MongoGateway, provides=MongoDBInterface, scope=Scope.APP)
    submissions_db = provide(SubmissionsDB, provides=SubmissionsDBInterface, scope=Scope.APP)
    task_cache_db = provide(TaskCacheDB, provides=TaskCacheInterface, scope=Scope.APP)
    drills_db = provide(DrillsDB, provides=DrillsDBInterface, scope=Scope.APP)
