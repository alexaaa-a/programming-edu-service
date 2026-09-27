from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.db.user_project_db import (
    UserProjectDBInterface,
)
from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface


class GetBoardUseCase:
    def __init__(
            self,
            task_db: TaskDBInterface,
            sprint_db: SprintDBInterface,
            user_project_db: UserProjectDBInterface,
    ) -> None:
        self.task_db = task_db
        self.sprint_db = sprint_db
        self.user_project_db = user_project_db

    async def __call__(self, user_id: int) -> dict[str, list[TaskDTO]] | None:
        active_sprint = await self.sprint_db.get_current_sprint(user_id)
        if active_sprint is None:
            return None

        tasks = await self.task_db.get_tasks(
            sprint_id=active_sprint.sprint_id, user_id=user_id
        )

        if tasks is None:
            return None

        return {
            "todo": [task for task in tasks if task.status == "todo"],
            "in_progress": [task for task in tasks if task.status == "in_progress"],
            "review": [task for task in tasks if task.status == "review"],
            "done": [task for task in tasks if task.status == "done"],
        }
