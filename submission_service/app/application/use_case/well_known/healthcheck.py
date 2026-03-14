from submission_service.app.application.interfaces.db.mongo_db import MongoDBInterface


class HealthCheckUseCase:
    def __init__(self, mongo_db: MongoDBInterface) -> None:
        self.mongo_db = mongo_db

    async def __call__(self) -> None:
        mongo_ok = await self.mongo_db.health()

        if not mongo_ok:
            raise RuntimeError("Not all databases are ready")
