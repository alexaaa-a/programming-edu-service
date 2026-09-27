from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from task_service.app.application.close_gate import ReviewSnapshot


@dataclass(frozen=True, slots=True)
class TrajectoryHint:
    action: str
    reason: str
    block_next_sprint: bool
    mastery: float = 0.0
    difficulty: float = 0.0
    pace: float = 0.0
    readiness: float = 0.0


class TaskReviewGatewayInterface(Protocol):
    @abstractmethod
    async def get_task_reviews(
            self,
            task_id: int,
            authorization: str,
    ) -> list[ReviewSnapshot] | None:
        raise NotImplementedError


class TrajectoryGatewayInterface(Protocol):
    @abstractmethod
    async def get_trajectory(
            self,
            authorization: str,
            task_id: int | None = None,
    ) -> TrajectoryHint | None:
        raise NotImplementedError
