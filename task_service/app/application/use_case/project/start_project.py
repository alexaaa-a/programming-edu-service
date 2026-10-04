import datetime
import logging
import uuid
from types import SimpleNamespace

from task_service.app.application.interfaces.db.user_project_db import UserProjectDBInterface
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.db.sprint_db import SprintDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.application.career import clear_incident_used, new_intern
from task_service.app.application.interfaces.career_llm import CareerLlmInterface
from task_service.app.application.peer_review import PEER_REVIEW_TITLE, compose_peer_review
from task_service.app.application.dto.user import UserProjectDTO
from task_service.app.application.dto.sprint import SprintDTO
from task_service.app.application.dto.task import TaskDTO

_logger = logging.getLogger("task_service.start_project")


class StartProjectUseCase:
    def __init__(
            self,
            user_project_db: UserProjectDBInterface,
            project_db: ProjectDBInterface,
            sprint_db: SprintDBInterface,
            task_db: TaskDBInterface,
            task_event_producer: TaskEventProducerInterface,
            career_db: CareerDBInterface,
            career_llm: CareerLlmInterface = None,  # type: ignore[assignment]
    ) -> None:
        self.user_project_db = user_project_db
        self.project_db = project_db
        self.sprint_db = sprint_db
        self.task_db = task_db
        self.task_event_producer = task_event_producer
        self.career_db = career_db
        self.career_llm = career_llm

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
            await self._rollback(
                user_id=user_id,
                user_project_id=new_project.user_project_id,
                sprint_id=None,
                published_tasks=[],
            )
            return None

        first_sprint_template = next(
            (s for s in template.sprints if s.order == 1),
            None,
        )
        published: list[tuple[int, str]] = []
        created_career = False
        try:
            if first_sprint_template is None or not first_sprint_template.tasks:
                raise RuntimeError("template_missing_sprint_1_tasks")
            now = datetime.datetime.now()
            created_tasks: list[TaskDTO] = []
            career = await self.career_db.get(user_id)
            if career is not None and career.incident_used:
                reset = clear_incident_used(career)
                if await self.career_db.save(reset):
                    career = reset
            grade = career.grade if career is not None else None
            template_tasks = list(first_sprint_template.tasks)
            extra = await compose_peer_review(grade, self.career_llm)
            if extra is not None and not any(task.title == PEER_REVIEW_TITLE for task in template_tasks):
                template_tasks.append(
                    SimpleNamespace(title=extra[0], description=extra[1], review_bug=extra[2])
                )
            for template_task in template_tasks:
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
                    review_bug=getattr(template_task, "review_bug", None),
                    hidden_tests=str(getattr(template_task, "tests", "") or ""),
                )
                task_created = await self.task_db.create_task(new_task)
                if not task_created:
                    raise RuntimeError("task_create_failed")
                created_tasks.append(new_task)
            for order, new_task in enumerate(created_tasks):
                await self.task_event_producer.produce_task_created(
                    task_id=new_task.task_id,
                    user_id=user_id,
                    status=new_task.status,
                    task_description=new_task.description,
                    title=new_task.title,
                    order=order,
                    tests=new_task.hidden_tests or None,
                )
                published.append((new_task.task_id, new_task.description))
            existing = await self.career_db.get(user_id)
            if existing is None:
                saved = await self.career_db.save(new_intern(user_id))
                if not saved:
                    raise RuntimeError("career_create_failed")
                created_career = True
        except Exception:
            _logger.exception(
                "start_project partial failure user_id=%s project_id=%s sprint_id=%s",
                user_id,
                new_project.user_project_id,
                new_sprint.sprint_id,
            )
            await self._rollback(
                user_id=user_id,
                user_project_id=new_project.user_project_id,
                sprint_id=new_sprint.sprint_id,
                published_tasks=published,
                drop_career=created_career,
            )
            return None

        return creation_project

    async def _rollback(
            self,
            user_id: int,
            user_project_id: int,
            sprint_id: int | None,
            published_tasks: list[tuple[int, str]],
            drop_career: bool = False,
    ) -> None:
        for task_id, description in published_tasks:
            try:
                await self.task_event_producer.produce_task_status_updated(
                    task_id=task_id,
                    user_id=user_id,
                    status="cancelled",
                    task_description=description,
                )
            except Exception:
                _logger.exception(
                    "start_project could not emit cancel for task_id=%s",
                    task_id,
                )
        if sprint_id is not None:
            deleted = await self.task_db.delete_tasks_by_sprint(sprint_id, user_id)
            if not deleted:
                _logger.error(
                    "start_project rollback could not delete tasks sprint_id=%s",
                    sprint_id,
                )
            cancelled = await self.sprint_db.update_sprint(
                user_id=user_id,
                old_status="active",
                new_status="cancelled",
                completed_at=None,
                close_mode=None,
                sprint_id=sprint_id,
            )
            if not cancelled:
                _logger.error(
                    "start_project rollback could not cancel sprint_id=%s",
                    sprint_id,
                )
        closed = await self.user_project_db.update_user_project(
            user_project_id,
            "cancelled",
            datetime.datetime.now(),
        )
        if not closed:
            _logger.error(
                "start_project rollback could not cancel user_project_id=%s",
                user_project_id,
            )
        if drop_career:
            await self.career_db.delete(user_id)

    @staticmethod
    def _generate_id() -> int:
        return uuid.uuid4().int % (2**53)
