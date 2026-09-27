import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.trajectory.planner import TaskInfo
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

    async def upsert_task(
            self,
            task_id: int,
            user_id: int,
            status: str,
            task_description: str | None = None,
            round_limit: int | None = None,
    ) -> bool:
        try:
            update: dict[str, Any] = {
                "task_id": task_id,
                "user_id": user_id,
                "status": status,
            }
            if task_description is not None:
                update["task_description"] = task_description
            if round_limit is not None:
                update["round_limit"] = round_limit

            await self._coll.update_one(
                {"task_id": task_id, "user_id": user_id},
                {"$set": update},
                upsert=True,
            )
            return True
        except Exception:
            self._logger.exception("Failed to upsert task in cache")
            return False

    async def delete_task(self, task_id: int, user_id: int) -> bool:
        try:
            await self._coll.delete_one({"task_id": task_id, "user_id": user_id})
            return True
        except Exception:
            self._logger.exception("Failed to delete task from cache")
            return False

    async def get_status(self, task_id: int, user_id: int) -> str | None:
        try:
            doc = await self._coll.find_one({"task_id": task_id, "user_id": user_id})
            if doc is None:
                return None
            return doc.get("status")
        except Exception:
            self._logger.exception("Failed to get task status from cache")
            return None

    async def get_task_description(self, task_id: int, user_id: int) -> str | None:
        try:
            doc = await self._coll.find_one({"task_id": task_id, "user_id": user_id})
            if doc is None:
                return None
            return doc.get("task_description")
        except Exception:
            self._logger.exception("Failed to get task description from cache")
            return None

    async def get_round_limit(self, task_id: int, user_id: int) -> int | None:
        try:
            doc = await self._coll.find_one({"task_id": task_id, "user_id": user_id})
            if doc is None or doc.get("round_limit") is None:
                return None
            return int(doc["round_limit"])
        except Exception:
            self._logger.exception("Failed to get round limit from cache")
            return None

    async def list_user_tasks(self, user_id: int) -> list[TaskInfo] | None:
        try:
            cursor = self._coll.find(
                {"user_id": user_id},
                {"_id": 0, "task_id": 1, "status": 1, "task_description": 1},
            )
            return [
                TaskInfo(
                    task_id=int(doc["task_id"]),
                    status=str(doc.get("status") or ""),
                    description=str(doc.get("task_description") or ""),
                )
                async for doc in cursor
                if doc.get("task_id") is not None
            ]
        except Exception:
            self._logger.exception("Failed to list user tasks from cache")
            return None
