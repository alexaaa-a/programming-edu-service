from datetime import datetime, timezone

from submission_service.app.application.interfaces.db.submissions_db import SubmissionsDBInterface
from submission_service.app.config import Settings
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.trajectory.formula import (
    TrajectoryConfig,
    TrajectoryResult,
    compute_trajectory,
)


class GetUserTrajectoryUseCase:
    def __init__(
            self,
            submissions_db: SubmissionsDBInterface,
            settings: Settings,
            task_cache: TaskCacheInterface,
    ) -> None:
        self._submissions_db = submissions_db
        self._task_cache = task_cache
        self._max_rounds = max(1, int(settings.review_loop_settings.max_rounds))

    async def __call__(
            self,
            user_id: int,
            task_id: int | None = None,
            now: datetime | None = None,
    ) -> TrajectoryResult:
        submissions = await self._submissions_db.get_all_user_submissions(user_id=user_id)
        current_status: str | None = None
        max_rounds = self._max_rounds
        if task_id is not None and self._task_cache is not None:
            current_status = await self._task_cache.get_status(task_id, user_id)
            getter = getattr(self._task_cache, "get_round_limit", None)
            if getter is not None:
                try:
                    raw = await getter(task_id, user_id)
                except Exception:
                    raw = None
                if isinstance(raw, int) and raw > max_rounds:
                    max_rounds = min(raw, self._max_rounds + 1)
        return compute_trajectory(
            submissions,
            task_id=task_id,
            now=now or datetime.now(tz=timezone.utc),
            config=TrajectoryConfig(max_rounds=max_rounds),
            current_task_status=current_status,
        )
