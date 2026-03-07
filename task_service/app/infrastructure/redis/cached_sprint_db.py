import datetime
import json
import logging

from task_service.app.application.dto.sprint import SprintDTO
from task_service.app.application.interfaces.db.cache import CacheInterface
from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.infrastructure.redis.cache_keys import CURRENT_SPRINT
from task_service.app.infrastructure.redis.serializer import dto_to_json


def _sprint_from_json(s: str) -> SprintDTO | None:
    try:
        d = json.loads(s)
        for key in ("started_at", "completed_at"):
            if d.get(key):
                d[key] = datetime.datetime.fromisoformat(
                    d[key].replace("Z", "+00:00")
                )
        return SprintDTO(**d)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


class CachedSprintDB(SprintDBInterface):
    def __init__(
        self,
        inner: SprintDBInterface,
        cache: CacheInterface,
        logger: logging.Logger,
        ttl_sec: int = 300,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._logger = logger
        self._ttl = ttl_sec

    def _key(self, user_id: int) -> str:
        return CURRENT_SPRINT.format(user_id=user_id)

    async def get_current_sprint(self, user_id: int) -> SprintDTO | None:
        key = self._key(user_id)
        raw = await self._cache.get(key)
        if raw is not None:
            dto = _sprint_from_json(raw)
            if dto is not None:
                return dto
        dto = await self._inner.get_current_sprint(user_id)
        if dto is not None:
            await self._cache.set(key, dto_to_json(dto), ttl_sec=self._ttl)
        return dto

    async def create_sprint(self, sprint: SprintDTO) -> bool:
        ok = await self._inner.create_sprint(sprint)
        if ok:
            await self._cache.delete(self._key(sprint.user_id))
        return ok

    async def update_sprint(
        self,
        user_id: int,
        old_status: str,
        new_status: str,
        completed_at: datetime.datetime | None = None,
    ) -> bool:
        ok = await self._inner.update_sprint(
            user_id, old_status, new_status, completed_at
        )
        if ok:
            await self._cache.delete(self._key(user_id))
        return ok
