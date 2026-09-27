from abc import abstractmethod
from typing import Protocol

from task_service.app.application.career import CareerState


class CareerDBInterface(Protocol):
    @abstractmethod
    async def get(self, user_id: int) -> CareerState | None:
        raise NotImplementedError

    @abstractmethod
    async def save(self, state: CareerState) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, user_id: int) -> bool:
        raise NotImplementedError
