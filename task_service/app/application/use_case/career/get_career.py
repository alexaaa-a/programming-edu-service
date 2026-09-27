from dataclasses import dataclass

from task_service.app.application.career import CareerState
from task_service.app.application.interfaces.db.career_db import CareerDBInterface


@dataclass(frozen=True, slots=True)
class GetCareerResult:
    state: CareerState | None = None
    error: str | None = None


class GetCareerUseCase:
    def __init__(self, career_db: CareerDBInterface) -> None:
        self._career_db = career_db

    async def __call__(self, user_id: int) -> GetCareerResult:
        state = await self._career_db.get(user_id)
        if state is None:
            return GetCareerResult(error="not_found")
        return GetCareerResult(state=state)
