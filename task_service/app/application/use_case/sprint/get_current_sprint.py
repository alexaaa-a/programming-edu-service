from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.application.dto.sprint import SprintDTO


class GetCurrentSprintUseCase:
    def __init__(self, sprint_db: SprintDBInterface) -> None:
        self.sprint_db = sprint_db

    async def __call__(self, user_id: int) -> SprintDTO | None:
        curr_sprint = await self.sprint_db.get_current_sprint(user_id)
        if not curr_sprint:
            return None

        return curr_sprint
