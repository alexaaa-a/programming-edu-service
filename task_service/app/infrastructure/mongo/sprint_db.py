import datetime
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from dataclasses import asdict

from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.application.dto.sprint import SprintDTO
from task_service.app.config import Settings


class SprintDB(SprintDBInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger
    ) -> None:
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["sprints"]
        self.logger = logger

    async def create_sprint(self, sprint: SprintDTO) -> bool:
        try:
            await self.db.insert_one(asdict(sprint))
            return True

        except Exception:
            self.logger.exception("Failed to create sprint")
            return False

    async def get_current_sprint(
            self,
            user_id: int
    ) -> SprintDTO:
        try:
            doc = await self.db.find_one({"user_id": user_id, "status": "active"})
            if not doc:
                return None

            data = dict(doc)
            data.pop("_id", None)

            return SprintDTO.from_document(data)

        except Exception:
            self.logger.exception("Failed to get current sprint")
            return None

    async def update_sprint(
            self,
            user_id: int,
            old_status: str,
            new_status: str,
            completed_at: datetime.datetime | None = None,
            close_mode: str | None = None,
            sprint_id: int | None = None,
    ) -> bool:
        try:
            payload: dict[str, Any] = {"status": new_status}
            update_doc: dict[str, Any] = {"$set": payload}
            if completed_at is not None:
                payload["completed_at"] = completed_at
            elif new_status == "active":
                update_doc["$unset"] = {"completed_at": "", "close_mode": ""}
            if close_mode is not None:
                payload["close_mode"] = close_mode
            query: dict[str, Any] = {"user_id": user_id, "status": old_status}
            if sprint_id is not None:
                query["sprint_id"] = sprint_id
            result = await self.db.update_one(query, update_doc)
            return result.matched_count > 0

        except Exception:
            self.logger.exception("Failed to update sprint")
            return False
