import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from dataclasses import asdict

from task_service.app.application.dto.project import (
    ProjectTemplateDTO,
    SprintOrderDTO,
    TaskDTO as ProjectTaskDTO,
)
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.config import Settings


class ProjectDB(ProjectDBInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger
    ) -> None:
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["project_templates"]
        self.logger = logger

    async def get_all_templates_for_user(
            self,
            exclude_ids: list[int],
            level: str,
            direction: str
    ) -> list[ProjectTemplateDTO] | None:
        try:
            data = self.db.find(
                {
                    "project_template_id": {"$nin": exclude_ids},
                    "level": level,
                    "direction": direction
                },
            )

            if data is None:
                return None

            templates = []
            async for template in data:
                templates.append(self._doc_to_template(template))
            return templates

        except Exception:
            self.logger.exception("Failed to get all templates")
            return None

    async def get_template_by_id(self, template_id: str) -> ProjectTemplateDTO | None:
        try:
            data = await self.db.find_one({"project_template_id": template_id})

            if data is None:
                return None

            return self._doc_to_template(data)

        except Exception:
            self.logger.exception("Failed to get template by id")
            return None

    async def create_template(self, template: ProjectTemplateDTO) -> bool:
        try:
            await self.db.insert_one(asdict(template))
            return True

        except Exception:
            self.logger.exception("Failed to create template")
            return False

    @staticmethod
    def _doc_to_template(doc: Any) -> ProjectTemplateDTO:
        d = dict(doc)
        d.pop("_id", None)
        sprints = []
        for s in d.get("sprints", []):
            tasks = [
                ProjectTaskDTO(title=t["title"], description=t["description"])
                for t in s.get("tasks", [])
            ]
            sprints.append(
                SprintOrderDTO(order=s["order"], title=s["title"], tasks=tasks)
            )
        d["sprints"] = sprints
        return ProjectTemplateDTO(**d)
