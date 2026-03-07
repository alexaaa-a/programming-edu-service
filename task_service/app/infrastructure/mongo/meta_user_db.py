import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface
from task_service.app.application.dto.user import MetaUserDTO
from task_service.app.config import Settings


class MetaUserDB(MetaUserDBInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger
    ) -> None:
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["meta_users"]
        self.logger = logger

    async def create_update_meta_user(self, user: MetaUserDTO) -> bool:
        try:
            await self.db.update_one(
                {"user_id": user.user_id},
                {"$set": {
                    "user_id": user.user_id,
                    "direction": user.direction,
                    "level": user.level
                }},
                upsert=True
            )
            return True

        except Exception:
            self.logger.exception("Failed to create or update meta user")
            return False

    async def get_meta_user(self, user_id: int) -> MetaUserDTO | None:
        try:
            doc = await self.db.find_one({"user_id": user_id})
            if not doc:
                return None

            data = dict(doc)
            data.pop("_id", None)

            return MetaUserDTO(**data)

        except Exception:
            self.logger.exception("Failed to get meta user")
            return None