import logging
from motor.motor_asyncio import AsyncIOMotorClient

from user_service.app.application.interfaces.db.mongo_db import MongoDBInterface


class MongoGateway(MongoDBInterface):
    def __init__(self, client: AsyncIOMotorClient, logger: logging.Logger) -> None:
        self._client = client
        self.logger = logger

    async def health(self) -> bool:
        try:
            await self._client.admin.command("ping")
            return True

        except Exception:
            self.logger.exception("Exception when connecting to Mongo")
            return False
