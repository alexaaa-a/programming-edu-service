import datetime
import json
import logging

from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.db.cache import CacheInterface
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.infrastructure.redis.cache_keys import SPRINT_TASKS


def _task_from_json(d: dict) -> TaskDTO:
    for key in ("created_at", "completed_at"):
        if d.get(key):
            d[key] = datetime.datetime.fromisoformat(
                d[key].replace("Z", "+00:00")
            )
    return TaskDTO.from_document(d)


def _tasks_list_from_json(s: str) -> list[TaskDTO] | None:
    try:
        data = json.loads(s)
        if not isinstance(data, list):
            return None
        return [_task_from_json(d) for d in data]
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


class CachedTaskDB(TaskDBInterface):
    def __init__(
            self,
            inner: TaskDBInterface,
            cache: CacheInterface,
            logger: logging.Logger,
            ttl_sec: int = 300,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._logger = logger
        self._ttl = ttl_sec

    def _key(self, sprint_id: int, user_id: int) -> str:
        return SPRINT_TASKS.format(sprint_id=sprint_id, user_id=user_id)

    async def get_tasks(
            self,
            sprint_id: int,
            user_id: int
    ) -> list[TaskDTO] | None:
        key = self._key(sprint_id, user_id)
        raw = await self._cache.get(key)
        if raw is not None:
            tasks = _tasks_list_from_json(raw)
            if tasks is not None:
                return tasks
        tasks = await self._inner.get_tasks(sprint_id, user_id)
        if tasks is not None:
            from dataclasses import asdict
            data = [asdict(t) for t in tasks]
            for item in data:
                for k in ("created_at", "completed_at"):
                    if item.get(k):
                        item[k] = item[k].isoformat()
            await self._cache.set(
                key, json.dumps(data), ttl_sec=self._ttl
            )
        return tasks

    async def create_task(self, task: TaskDTO) -> bool:
        ok = await self._inner.create_task(task)
        if ok:
            await self._cache.delete(
                self._key(task.sprint_id, task.user_id)
            )
        return ok

    async def update_task(
            self,
            task_id: int,
            new_status: str,
            completed_at: datetime.datetime | None = None,
            close_quality: str | None = None,
            user_id: int | None = None,
            close_note: str | None = None,
    ) -> bool:
        ok = await self._inner.update_task(
            task_id,
            new_status,
            completed_at,
            close_quality,
            user_id=user_id,
            close_note=close_note,
        )
        if ok:
            task = (
                await self._inner.get_task_by_id(task_id, user_id)
                if user_id is not None
                else await self._inner.get_task_by_task_id(task_id)
            )
            if task is not None:
                await self._cache.delete(
                    self._key(task.sprint_id, task.user_id)
                )
        return ok

    async def get_task_by_id(self, task_id: int, user_id: int) -> TaskDTO | None:
        return await self._inner.get_task_by_id(task_id, user_id)

    async def get_task_by_task_id(self, task_id: int) -> TaskDTO | None:
        return await self._inner.get_task_by_task_id(task_id)

    async def delete_tasks_by_sprint(self, sprint_id: int, user_id: int) -> bool:
        ok = await self._inner.delete_tasks_by_sprint(sprint_id, user_id)
        if ok:
            await self._cache.delete(self._key(sprint_id, user_id))
        return ok
