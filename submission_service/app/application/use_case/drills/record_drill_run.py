import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from submission_service.app.application.drills.bank import DRILL_BY_ID
from submission_service.app.application.drills.models import DrillRun
from submission_service.app.application.interfaces.db.drills_db import DrillsDBInterface

_logger = logging.getLogger("submission_service.drills")


@dataclass(frozen=True, slots=True)
class RecordDrillResult:
    stored: bool
    run: DrillRun | None = None
    error: str = ""


class RecordDrillRunUseCase:
    def __init__(self, drills_db: DrillsDBInterface) -> None:
        self._drills_db = drills_db

    async def __call__(
            self,
            user_id: int,
            drill_id: str,
            passed: int,
            total: int,
            at: datetime | None = None,
    ) -> RecordDrillResult:
        drill = DRILL_BY_ID.get(drill_id)
        if drill is None:
            return RecordDrillResult(stored=False, error="unknown_drill")
        if total <= 0:
            return RecordDrillResult(stored=False, error="empty_run")

        safe_total = min(int(total), 100)
        run = DrillRun(
            drill_id=drill.id,
            skill_id=drill.skill_id,
            passed=max(0, min(int(passed), safe_total)),
            total=safe_total,
            at=at or datetime.now(tz=timezone.utc),
        )
        stored = await self._drills_db.add_run(user_id, run)
        if not stored:
            _logger.warning("drill.run.not_stored user_id=%s drill=%s", user_id, drill.id)
        return RecordDrillResult(stored=stored, run=run)
