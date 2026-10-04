import json
import logging

from task_service.app.application.dto.project import (
    ProjectTemplateDTO,
    SprintOrderDTO,
    TaskDTO as ProjectTaskDTO,
)
from task_service.app.application.interfaces.db.cache import CacheInterface
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.infrastructure.redis.cache_keys import TEMPLATE
from task_service.app.infrastructure.redis.serializer import dto_to_json


def _template_from_json(s: str) -> ProjectTemplateDTO | None:
    try:
        d = json.loads(s)
        sprints = []
        for s_data in d.get("sprints", []):
            tasks = [
                ProjectTaskDTO(
                    title=t["title"],
                    description=t["description"],
                    tests=str(t.get("tests") or ""),
                )
                for t in s_data.get("tasks", [])
            ]
            sprints.append(
                SprintOrderDTO(
                    order=s_data["order"],
                    title=s_data["title"],
                    tasks=tasks,
                )
            )
        return ProjectTemplateDTO(
            project_template_id=d.get("project_template_id"),
            title=d["title"],
            description=d["description"],
            sprints=sprints,
            direction=d["direction"],
            level=d["level"],
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


class CachedProjectDB(ProjectDBInterface):
    def __init__(
            self,
            inner: ProjectDBInterface,
            cache: CacheInterface,
            logger: logging.Logger,
            ttl_sec: int = 300,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._logger = logger
        self._ttl = ttl_sec

    def _key(self, template_id: int | str) -> str:
        return TEMPLATE.format(template_id=template_id)

    async def get_template_by_id(
            self,
            template_id: int | str
    ) -> ProjectTemplateDTO | None:
        template_id_str = str(template_id)
        key = self._key(template_id_str)
        raw = await self._cache.get(key)
        if raw is not None:
            dto = _template_from_json(raw)
            if dto is not None:
                return dto
        dto = await self._inner.get_template_by_id(template_id_str)
        if dto is not None:
            await self._cache.set(key, dto_to_json(dto), ttl_sec=self._ttl)
        return dto

    async def get_all_templates_for_user(
            self,
            exclude_ids: list[int],
            level: str,
            direction: str,
    ) -> list[ProjectTemplateDTO] | None:
        return await self._inner.get_all_templates_for_user(
            exclude_ids, level, direction
        )

    async def create_template(self, template: ProjectTemplateDTO) -> bool:
        ok = await self._inner.create_template(template)
        if ok and template.project_template_id is not None:
            await self._cache.delete(
                self._key(str(template.project_template_id))
            )
        return ok
