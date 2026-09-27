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
                tasks.append(TaskDTO.from_document(doc))

            return tasks

        except Exception:
            self.logger.exception("Failed to get tasks")
            return None

    async def update_task(
            self,
            task_id: int,
            new_status: str,
            completed_at: datetime.datetime | None = None,
            close_quality: str | None = None,
            user_id: int | None = None,
            close_note: str | None = None,
    ) -> bool:
        try:
            payload: dict[str, Any] = {
                "status": new_status,
                "completed_at": completed_at,
            }
            update_doc: dict[str, Any] = {"$set": payload}
            unset: dict[str, str] = {}
            if close_quality is not None:
                payload["close_quality"] = close_quality
            elif new_status != "done":
                unset["close_quality"] = ""
            if close_note:
                payload["close_note"] = close_note
            elif close_note == "":
                unset["close_note"] = ""
            if unset:
                update_doc["$unset"] = unset
            query: dict[str, Any] = {"task_id": task_id}
            if user_id is not None:
                query["user_id"] = user_id
            result = await self.db.update_one(query, update_doc)
            return bool(getattr(result, "matched_count", 0))

        except Exception:
            self.logger.exception("Failed to update task")
            return False

    async def get_task_by_id(self, task_id: int, user_id: int) -> TaskDTO | None:
        try:
            doc = await self.db.find_one({"task_id": task_id, "user_id": user_id})
            if not doc:
                return None

            return TaskDTO.from_document(doc)

        except Exception:
            self.logger.exception("Failed to get task by id")
            return None

    async def get_task_by_task_id(self, task_id: int) -> TaskDTO | None:
        try:
            doc = await self.db.find_one({"task_id": task_id})
            if not doc:
                return None

            return TaskDTO.from_document(doc)

        except Exception:
            self.logger.exception("Failed to get task by task_id")
            return None

    async def delete_tasks_by_sprint(self, sprint_id: int, user_id: int) -> bool:
        try:
            result = await self.db.delete_many({"sprint_id": sprint_id, "user_id": user_id})
            return True if result is not None else False
        except Exception:
            self.logger.exception(
                "Failed to delete tasks for sprint_id=%s user_id=%s",
                sprint_id,
                user_id,
            )
            return False
