import datetime
import json
import logging

from task_service.app.application.dto.user import UserProjectDTO
from task_service.app.application.interfaces.db.cache import CacheInterface
from task_service.app.application.interfaces.db.user_project_db import (
    UserProjectDBInterface,
)
from task_service.app.infrastructure.redis.cache_keys import ACTIVE_USER_PROJECT
from task_service.app.infrastructure.redis.serializer import dto_to_json


def _user_project_from_json(s: str) -> UserProjectDTO | None:
    try:
        d = json.loads(s)
        for key in ("created_at", "completed_at"):
            if d.get(key):
                d[key] = datetime.datetime.fromisoformat(
                    d[key].replace("Z", "+00:00")
                )
        return UserProjectDTO(**d)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


class CachedUserProjectDB(UserProjectDBInterface):
    def __init__(
            self,
            inner: UserProjectDBInterface,
            cache: CacheInterface,
            logger: logging.Logger,
            ttl_sec: int = 300,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._logger = logger
        self._ttl = ttl_sec

    def _key(self, user_id: int) -> str:
        return ACTIVE_USER_PROJECT.format(user_id=user_id)

    async def get_active_user_project(self, user_id: int) -> UserProjectDTO | None:
        key = self._key(user_id)
        raw = await self._cache.get(key)
        if raw is not None:
            dto = _user_project_from_json(raw)
            if dto is not None:
                return dto
        dto = await self._inner.get_active_user_project(user_id)
        if dto is not None:
            await self._cache.set(key, dto_to_json(dto), ttl_sec=self._ttl)
        return dto

    async def get_all_user_projects(self, user_id: int) -> list[UserProjectDTO] | None:
        return await self._inner.get_all_user_projects(user_id)

    async def create_user_project(self, user_project: UserProjectDTO) -> bool:
        ok = await self._inner.create_user_project(user_project)
        if ok:
            await self._cache.delete(self._key(user_project.user_id))
        return ok

    async def _invalidate_for_user_project(self, user_project_id: int) -> None:
        user_id = await self._inner.get_user_id_by_user_project_id(user_project_id)
        if user_id is not None:
            await self._cache.delete(self._key(user_id))

    async def update_user_project(
            self,
            user_project_id: int,
            new_status: str,
            completed_at: datetime.datetime,
    ) -> bool:
        ok = await self._inner.update_user_project(
            user_project_id, new_status, completed_at
        )
        if ok:
            await self._invalidate_for_user_project(user_project_id)
        return ok

    async def update_current_sprint_order(
            self,
            user_project_id: int,
            new_sprint_order: int,
    ) -> bool:
        ok = await self._inner.update_current_sprint_order(
            user_project_id, new_sprint_order
        )
        if ok:
            await self._invalidate_for_user_project(user_project_id)
        return ok
