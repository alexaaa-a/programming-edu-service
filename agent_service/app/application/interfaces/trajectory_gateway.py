from typing import Protocol

from agent_service.app.application.trajectory import TrajectorySnapshot


class TrajectoryGatewayInterface(Protocol):
    async def get_trajectory(
            self,
            authorization: str,
            task_id: int | None = None,
    ) -> TrajectorySnapshot | None:
        raise NotImplementedError
