import logging
import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from dataclasses import asdict

from task_service.app.application.dto.user import UserProjectDTO
from task_service.app.application.interfaces.db.user_project_db import (
    UserProjectDBInterface,
)
from task_service.app.config import Settings


class UserProjectDB(UserProjectDBInterface):
    def __init__(
        self,
        client: AsyncIOMotorClient[Any],
        settings: Settings,
        logger: logging.Logger,
    ) -> None:
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["user_projects"]
        self.logger = logger

    async def get_user_id_by_user_project_id(
        self, user_project_id: int
    ) -> int | None:
        try:
            doc = await self.db.find_one(
                {"user_project_id": user_project_id},
                {"user_id": 1},
            )
            return doc["user_id"] if doc else None
        except Exception:
            self.logger.exception(
                "Failed to get user_id by user_project_id=%s",
                user_project_id,
            )
            return None

    async def get_active_user_project(self, user_id: int) -> UserProjectDTO | None:
        try:
            data = await self.db.find_one(
                {"user_id": user_id, "status": "active"}
            )

            if data is None:
                return None

            data_dict = dict(data)
            data_dict.pop("_id")
            return UserProjectDTO(**data_dict)

        except Exception:
            self.logger.exception("Failed to get active user project")
            return None

    async def get_all_user_projects(self, user_id: int) -> list[UserProjectDTO] | None:
        try:
            data = self.db.find(
                {"user_id": user_id}
            )

            if data is None:
                return None

            user_projects = []
            async for project in data:
                project_dict = dict(project)
                project_dict.pop("_id")

                user_projects.append(UserProjectDTO(**project_dict))

            return user_projects

        except Exception:
            self.logger.exception("Failed to get all user projects")
            return None

    async def create_user_project(self, user_project: UserProjectDTO) -> bool:
        try:
            await self.db.insert_one(asdict(user_project))
            return True

        except Exception:
            self.logger.exception("Failed to create user project")
            return False

    async def update_user_project(
            self,
            user_project_id: int,
            new_status: str,
            completed_at: datetime.datetime
    ) -> bool:
        try:
            await self.db.update_one(
                {"user_project_id": user_project_id},
                {"$set": {"status": new_status, "completed_at": completed_at}}
            )
            return True

        except Exception:
            self.logger.exception("Error when updating user project")
            return False

    async def update_current_sprint_order(
            self,
            user_project_id: int,
            new_sprint_order: int
    ) -> bool:
        try:
            await self.db.update_one(
                {"user_project_id": user_project_id},
                {"$set": {"current_sprint_order": new_sprint_order}}
            )
            return True

        except Exception:
            self.logger.exception("Error when updating current sprint order")
            return False
