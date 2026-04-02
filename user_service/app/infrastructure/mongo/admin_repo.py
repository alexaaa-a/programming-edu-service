import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from user_service.app.application.dto import AdminDTO
from user_service.app.application.interfaces.db.admin_repo import AdminRepositoryInterface
from user_service.app.config import Settings


class AdminRepository(AdminRepositoryInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger
    ):
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["admins"]
        self.logger = logger

    async def get_role(self, user_id: int) -> str | None:
        try:
            doc = await self.db.find_one({"user_id": user_id})
            if doc is None:
                return None
            role = doc.get("role")
            return str(role) if role is not None else None
        except Exception:
            self.logger.exception("Failed to get admin role for user_id=%s", user_id)
            return None

    async def set_admin(self, user_id: int) -> bool:
        try:
            await self.db.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "role": "admin"}},
                upsert=True,
            )
            return True
        except Exception:
            self.logger.exception("Failed to set admin role for user_id=%s", user_id)
            return False

    async def delete_admin(self, user_id: int) -> bool:
        try:
            result = await self.db.delete_one({"user_id": user_id, "role": "admin"})
            return result.deleted_count > 0
        except Exception:
            self.logger.exception("Failed to delete admin role for user_id=%s", user_id)
            return False

    async def get_all_admins(self) -> list[AdminDTO]:
        try:
            result: list[AdminDTO] = []
            cursor = self.db.find({}, {"_id": 0, "user_id": 1, "role": 1}).sort("user_id", 1)
            async for doc in cursor:
                user_id = doc.get("user_id")
                role = doc.get("role")
                if isinstance(user_id, int) and isinstance(role, str):
                    result.append(AdminDTO(user_id=user_id, role=role))
            return result
        except Exception:
            self.logger.exception("Failed to get admins list")
            return []
