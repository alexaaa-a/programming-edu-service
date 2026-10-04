import datetime
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from submission_service.app.application.drills.models import DrillRun
from submission_service.app.application.interfaces.db.drills_db import DrillsDBInterface
from submission_service.app.config import Settings


class DrillsDB(DrillsDBInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger,
    ) -> None:
        self._client = client[settings.mongo_settings.name]
        self._logger = logger
        self._coll = self._client["drill_runs"]

    async def add_run(self, user_id: int, run: DrillRun) -> bool:
        try:
            await self._coll.insert_one(
                {
                    "user_id": user_id,
                    "drill_id": run.drill_id,
                    "skill_id": run.skill_id,
                    "passed": int(run.passed),
                    "total": int(run.total),
                    "at": run.at,
                }
            )
            return True
        except Exception:
            self._logger.exception("Exception when writing a drill run")
            return False

    async def list_runs(self, user_id: int, limit: int = 200) -> list[DrillRun]:
        try:
            cursor = self._coll.find({"user_id": user_id}).sort("at", -1).limit(max(1, min(int(limit), 1000)))
            docs = await cursor.to_list(None)
        except Exception:
            self._logger.exception("Exception when reading drill runs")
            return []
        runs: list[DrillRun] = []
        for doc in reversed(docs):
            at = doc.get("at")
            if not isinstance(at, datetime.datetime):
                continue
            runs.append(
                DrillRun(
                    drill_id=str(doc.get("drill_id") or ""),
                    skill_id=str(doc.get("skill_id") or ""),
                    passed=int(doc.get("passed") or 0),
                    total=int(doc.get("total") or 0),
                    at=at,
                )
            )
        return [run for run in runs if run.drill_id and run.skill_id]
