import logging
from datetime import datetime, timezone

from submission_service.app.application.drills.models import DrillPick
from submission_service.app.application.drills.select import choose_drill
from submission_service.app.application.interfaces.db.drills_db import DrillsDBInterface
from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.trajectory.formula import compute_knowledge
from submission_service.app.application.trajectory.planner import TaskInfo

_logger = logging.getLogger("submission_service.drills")


class GetDrillUseCase:
    def __init__(
            self,
            submissions_db: SubmissionsDBInterface,
            drills_db: DrillsDBInterface,
            task_cache: TaskCacheInterface,
    ) -> None:
        self._submissions_db = submissions_db
        self._drills_db = drills_db
        self._task_cache = task_cache

    async def __call__(self, user_id: int, now: datetime | None = None) -> DrillPick | None:
        stamp = now or datetime.now(tz=timezone.utc)
        submissions = await self._submissions_db.get_all_user_submissions(user_id=user_id) or []
        runs = await self._drills_db.list_runs(user_id)
        knowledge = compute_knowledge(
            submissions,
            descriptions=await self._descriptions(user_id),
            drill_runs=runs,
            now=stamp,
        )
        return choose_drill(knowledge, runs, now=stamp)

    async def _descriptions(self, user_id: int) -> dict[int, str]:
        lister = getattr(self._task_cache, "list_user_tasks", None)
        if lister is None:
            return {}
        try:
            tasks = await lister(user_id)
        except Exception:
            _logger.exception("Exception when listing user tasks for a drill")
            return {}
        return {
            task.task_id: task.description
            for task in (tasks or [])
            if isinstance(task, TaskInfo) and task.description
        }
