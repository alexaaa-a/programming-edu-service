from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from motor.motor_asyncio import AsyncIOMotorClient

from task_service.app.config import Settings
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.db.mongodb import MongoDBInterface
from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface
from task_service.app.application.interfaces.db.user_project_db import UserProjectDBInterface
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.infrastructure.mongo.gateway import MongoGateway
from task_service.app.infrastructure.mongo.task_db import TaskDB
from task_service.app.infrastructure.mongo.sprint_db import SprintDB
from task_service.app.infrastructure.mongo.project_db import ProjectDB
from task_service.app.infrastructure.mongo.meta_user_db import MetaUserDB
from task_service.app.infrastructure.mongo.user_project_db import UserProjectDB
from task_service.app.infrastructure.mongo.career_db import CareerDB


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
    meta_user_db = provide(MetaUserDB, provides=MetaUserDBInterface, scope=Scope.APP)
    user_project_db = provide(UserProjectDB, provides=UserProjectDBInterface, scope=Scope.APP)
    project_db = provide(ProjectDB, provides=ProjectDBInterface, scope=Scope.APP)
    sprint_db = provide(SprintDB, provides=SprintDBInterface, scope=Scope.APP)
    task_db = provide(TaskDB, provides=TaskDBInterface, scope=Scope.APP)
    career_db = provide(CareerDB, provides=CareerDBInterface, scope=Scope.APP)
