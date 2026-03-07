import datetime
import logging

from motor.motor_asyncio import AsyncIOMotorClient
from dataclasses import asdict
from typing import Any

from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.config import Settings


class TaskDB(TaskDBInterface):
    def __init__(
        self,
        client: AsyncIOMotorClient[Any],
        logger: logging.Logger,
        settings: Settings,
    ):
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["tasks"]
        self.logger = logger

    async def create_task(self, task: TaskDTO) -> bool:
        try:
            await self.db.insert_one(asdict(task))
            return True

        except Exception:
            self.logger.exception("Failed to insert task")
            return False

    async def get_tasks(self, sprint_id: int, user_id: int) -> list[TaskDTO] | None:
        try:
            docs = await self.db.find({"sprint_id": sprint_id, "user_id": user_id}).to_list(None)
            if not docs:
                return None

            tasks = []
            for doc in docs:
                doc.pop("_id")
                tasks.append(TaskDTO(**doc))

            return tasks

        except Exception:
            self.logger.exception("Failed to get tasks")
            return None

    async def update_task(
            self,
            task_id: int,
            new_status: str,
            completed_at: datetime.datetime | None = None,
    ) -> bool:
        try:
            if completed_at is None:
                await self.db.update_one(
                    {"task_id": task_id},
                    {"$set": {"status": new_status}},
                )
            else:
                await self.db.update_one(
                    {"task_id": task_id},
                    {"$set": {"status": new_status, "completed_at": completed_at}},
                )
            return True

        except Exception:
            self.logger.exception("Failed to update task")
            return False

    async def get_task_by_id(self, task_id: int, user_id: int) -> TaskDTO | None:
        try:
            doc = await self.db.find_one({"task_id": task_id, "user_id": user_id})
            if not doc:
                return None

            task = dict(doc)
            task.pop("_id")

            return TaskDTO(**task)

        except Exception:
            self.logger.exception("Failed to get task by id")
            return None

    async def get_task_by_task_id(self, task_id: int) -> TaskDTO | None:
        try:
            doc = await self.db.find_one({"task_id": task_id})
            if not doc:
                return None

            task = dict(doc)
            task.pop("_id", None)

            return TaskDTO(**task)

        except Exception:
            self.logger.exception("Failed to get task by task_id")
            return None
