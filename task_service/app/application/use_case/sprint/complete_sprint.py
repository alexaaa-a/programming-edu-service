import datetime
import uuid

from task_service.app.application.dto.sprint import SprintDTO
from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.db.user_project_db import (
    UserProjectDBInterface,
)
from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.application.interfaces.db.project_db import (
    ProjectDBInterface,
)


class CompleteSprintUseCase:
    TASK_COMPLETED = "done"
    SPRINT_COMPLETED = "completed"
    PROJECT_COMPLETED = "completed"
    PROJECT_FINISHED = "project finished"
    NEW_PROJECT = "new sprint created"

    def __init__(
            self,
            task_db: TaskDBInterface,
            sprint_db: SprintDBInterface,
            user_project_db: UserProjectDBInterface,
            project_db: ProjectDBInterface,
    ) -> None:
        self.task_db = task_db
        self.sprint_db = sprint_db
        self.user_project_db = user_project_db
        self.project_db = project_db

    async def __call__(self, user_id: int) -> bool | str | None:
        active_project = await self.user_project_db.get_active_user_project(user_id)
        if active_project is None:
            return None

        active_sprint = await self.sprint_db.get_current_sprint(user_id)
        if active_sprint is None:
            return None

        tasks = await self.task_db.get_tasks(active_sprint.sprint_id, user_id)
        if tasks is None:
            return None

        if not all(task.status == self.TASK_COMPLETED for task in tasks):
            return False

        now = datetime.datetime.now()
        update_sprint = await self.sprint_db.update_sprint(
            user_id=user_id,
            old_status="active",
            new_status=self.SPRINT_COMPLETED,
            completed_at=now,
        )
        if not update_sprint:
            return None

        user_project = active_project
        template = await self.project_db.get_template_by_id(
            user_project.template_id
        )
        if template is None:
            return None

        next_sprint_template = next(
            (s for s in template.sprints if s.order == active_sprint.order + 1),
            None,
        )

        if next_sprint_template is None:
            update_user_project = await self.user_project_db.update_user_project(
                user_project_id=user_project.user_project_id,
                new_status=self.PROJECT_COMPLETED,
                completed_at=now,
            )
            if not update_user_project:
                return None
            return self.PROJECT_FINISHED

        new_sprint_id = self._generate_id()
        new_sprint = SprintDTO(
            sprint_id=new_sprint_id,
            user_project_id=user_project.user_project_id,
            user_id=user_id,
            order=next_sprint_template.order,
            status="active",
            started_at=now,
            completed_at=None,
        )
        created = await self.sprint_db.create_sprint(new_sprint)
        if not created:
            return None

        for template_task in next_sprint_template.tasks:
            new_task = TaskDTO(
                task_id=self._generate_id(),
                user_id=user_id,
                user_project_id=user_project.user_project_id,
                sprint_id=new_sprint_id,
                title=template_task.title,
                description=template_task.description,
                status="todo",
                created_at=now,
                completed_at=None,
            )
            task_created = await self.task_db.create_task(new_task)
            if not task_created:
                return None

        new_order = user_project.current_sprint_order + 1
        order_updated = await self.user_project_db.update_current_sprint_order(
            user_project_id=user_project.user_project_id,
            new_sprint_order=new_order,
        )
        if not order_updated:
            return None

        return self.NEW_PROJECT

    @staticmethod
    def _generate_id() -> int:
        return uuid.uuid4().int % (2**53)
