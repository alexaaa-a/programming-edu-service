from abc import abstractmethod
from typing import Protocol

from submission_service.app.application.drills.models import DrillRun


class DrillsDBInterface(Protocol):
    @abstractmethod
    async def add_run(self, user_id: int, run: DrillRun) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def list_runs(self, user_id: int, limit: int = 200) -> list[DrillRun]:
        raise NotImplementedError
