import datetime
import uuid

from task_service.app.application.interfaces.db.user_project_db import UserProjectDBInterface
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.application.dto.user import UserProjectDTO
from task_service.app.application.dto.sprint import SprintDTO
from task_service.app.application.dto.task import TaskDTO


class StartProjectUseCase:
    def __init__(
            self,
            user_project_db: UserProjectDBInterface,
            project_db: ProjectDBInterface,
            sprint_db: SprintDBInterface,
            task_db: TaskDBInterface,
            task_event_producer: TaskEventProducerInterface,
    ) -> None:
        self.user_project_db = user_project_db
        self.project_db = project_db
        self.sprint_db = sprint_db
        self.task_db = task_db
        self.task_event_producer = task_event_producer

    async def __call__(self, user_id: int, template_id: int) -> bool | None:
        active_project = await self.user_project_db.get_active_user_project(user_id)
        if active_project:
            return None

        template = await self.project_db.get_template_by_id(template_id)
        if template is None:
            return None

        new_project = UserProjectDTO(
            user_project_id=self._generate_id(),
            user_id=user_id,
            template_id=template_id,
            status="active",
            current_sprint_order=1,
            created_at=datetime.datetime.now(),
            completed_at=None
        )
        creation_project = await self.user_project_db.create_user_project(new_project)
        if not creation_project:
            return None

        new_sprint = SprintDTO(
            sprint_id=self._generate_id(),
            user_project_id=new_project.user_project_id,
            user_id=new_project.user_id,
            order=1,
            status="active",
            started_at=datetime.datetime.now(),
            completed_at=None,
        )
        creation_sprint = await self.sprint_db.create_sprint(new_sprint)
        if not creation_sprint:
            return None

        first_sprint_template = next(
            (s for s in template.sprints if s.order == 1),
            None,
        )
        if first_sprint_template:
            now = datetime.datetime.now()
            for template_task in first_sprint_template.tasks:
                new_task = TaskDTO(
                    task_id=self._generate_id(),
                    user_id=user_id,
                    user_project_id=new_project.user_project_id,
                    sprint_id=new_sprint.sprint_id,
                    title=template_task.title,
                    description=template_task.description,
                    status="todo",
                    created_at=now,
                    completed_at=None,
                )
                task_created = await self.task_db.create_task(new_task)
                if not task_created:
                    return None
                await self.task_event_producer.produce_task_created(
                    task_id=new_task.task_id,
                    user_id=user_id,
                    status=new_task.status,
                    task_description=new_task.description,
                )

        return creation_project

    @staticmethod
    def _generate_id() -> int:
        return uuid.uuid4().int % (2**53)