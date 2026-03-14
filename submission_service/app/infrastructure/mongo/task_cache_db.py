import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.config import Settings


class TaskCacheDB(TaskCacheInterface):
    def __init__(
        self,
        client: AsyncIOMotorClient[Any],
        settings: Settings,
        logger: logging.Logger,
    ) -> None:
        self._client = client[settings.mongo_settings.name]
        self._logger = logger
        self._coll = self._client["task_cache"]

    async def upsert_task(self, task_id: int, user_id: int, status: str) -> None:
        try:
            await self._coll.update_one(
                {"task_id": task_id, "user_id": user_id},
                {"$set": {"task_id": task_id, "user_id": user_id, "status": status}},
                upsert=True,
            )
        except Exception:
            self._logger.exception("Failed to upsert task in cache")

    async def get_status(self, task_id: int, user_id: int) -> str | None:
        try:
            doc = await self._coll.find_one({"task_id": task_id, "user_id": user_id})
            if doc is None:
                return None
            return doc.get("status")
        except Exception:
            self._logger.exception("Failed to get task status from cache")
            return None
