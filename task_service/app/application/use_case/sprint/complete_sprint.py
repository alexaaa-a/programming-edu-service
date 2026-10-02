import datetime
import logging
import uuid
from dataclasses import dataclass, replace
from typing import Any

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
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.application.interfaces.review_gateway import (
    TaskReviewGatewayInterface,
    TrajectoryGatewayInterface,
)
from task_service.app.application.interfaces.career_llm import CareerLlmInterface
from task_service.app.application.night_incident import (
    graded_tasks,
    incident_outcome,
    incomplete_sprint_message,
    required_tasks_done,
)
from task_service.app.application.peer_review import (
    PEER_REVIEW_TITLE,
    compose_peer_review,
    is_peer_review_task,
)
from task_service.app.application.weak_tail import append_weak_tail, failed_criterion_from_latest
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.application.career import (
    CareerLetter,
    FridayDemo,
    accept_letter,
    draft_sprint_letter,
    new_intern,
)
from task_service.app.application.friday_demo import build_friday_demo, score_friday_demo
from task_service.app.application.quests import apply_demo, award
from task_service.app.application.sprint_hold import evaluate_sprint_hold

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompleteSprintResult:
    ok: bool = False
    error: str | None = None
    message: str | None = None
    status: str | None = None
    forced: bool = False
    weak_count: int = 0
    task_count: int = 0
    letter: CareerLetter | None = None
    demo: FridayDemo | None = None
    unlocked: tuple[str, ...] = ()


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
            task_event_producer: TaskEventProducerInterface,
            trajectory_gateway: TrajectoryGatewayInterface,
            career_db: CareerDBInterface,
            review_gateway: TaskReviewGatewayInterface = None,  # type: ignore[assignment]
            career_llm: CareerLlmInterface = None,  # type: ignore[assignment]
    ) -> None:
        self.task_db = task_db
        self.sprint_db = sprint_db
        self.user_project_db = user_project_db
        self.project_db = project_db
        self.task_event_producer = task_event_producer
        self.trajectory_gateway = trajectory_gateway
        self.career_db = career_db
        self.review_gateway = review_gateway
        self.career_llm = career_llm

    async def __call__(
            self,
            user_id: int,
            authorization: str | None = None,
            force: bool = False,
            consume_appeal: bool = False,
    ) -> CompleteSprintResult:
        active_project = await self.user_project_db.get_active_user_project(user_id)
        if active_project is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")

        active_sprint = await self.sprint_db.get_current_sprint(user_id)
        if active_sprint is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")

        tasks = await self.task_db.get_tasks(active_sprint.sprint_id, user_id)
        if tasks is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")

        if not required_tasks_done(tasks):
            return CompleteSprintResult(
                error="tasks_open",
                message=incomplete_sprint_message(tasks),
            )

        graded = graded_tasks(tasks)
        anchor_task_id = graded[-1].task_id if graded else None
        hint = await self.trajectory_gateway.get_trajectory(
            authorization or "",
            task_id=anchor_task_id,
        )
        decision = evaluate_sprint_hold(graded, hint)
        if decision.hold and decision.code != "trajectory" and not force:
            return CompleteSprintResult(
                error="hold",
                message=decision.reason,
                weak_count=decision.weak_count,
                task_count=decision.task_count,
            )

        template = await self.project_db.get_template_by_id(active_project.template_id)
        if template is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")

        next_sprint_template = next(
            (s for s in template.sprints if s.order == active_sprint.order + 1),
            None,
        )

        if next_sprint_template is not None and not next_sprint_template.tasks:
            return CompleteSprintResult(
                error="empty_next_sprint",
                message="Шаблон следующего спринта без задач — спринт не закрыт.",
            )

        career = await self.career_db.get(user_id) or new_intern(user_id)
        if career.pending_letter is not None:
            return CompleteSprintResult(
                ok=True,
                status="letter",
                forced=career.pending_forced,
                letter=career.pending_letter,
            )
        if career.pending_demo is not None:
            return CompleteSprintResult(
                ok=True,
                status="demo",
                forced=career.pending_forced,
                demo=career.pending_demo,
            )
        demo = await self._open_demo(tasks, authorization, trajectory_blocked=decision.hold)
        career = replace(
            career,
            appeal_used=True if consume_appeal else career.appeal_used,
            pending_letter=None,
            pending_forced=force,
            pending_demo=demo,
        )
        if not await self.career_db.save(career):
            return CompleteSprintResult(error="update_failed", message="Не удалось сохранить демо")
        return CompleteSprintResult(
            ok=True,
            status="demo",
            forced=career.pending_forced,
            demo=demo,
        )

    async def submit_demo(
            self,
            user_id: int,
            pitch: str,
            answer: str,
    ) -> CompleteSprintResult:
        if not pitch.strip() or not answer.strip():
            return CompleteSprintResult(
                error="empty",
                message="Напиши питч и ответ на вопрос Сары.",
            )
        active_project = await self.user_project_db.get_active_user_project(user_id)
        if active_project is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")
        active_sprint = await self.sprint_db.get_current_sprint(user_id)
        if active_sprint is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")
        tasks = await self.task_db.get_tasks(active_sprint.sprint_id, user_id)
        if tasks is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")
        if not required_tasks_done(tasks):
            return CompleteSprintResult(
                error="tasks_open",
                message=incomplete_sprint_message(tasks),
            )
        career = await self.career_db.get(user_id)
        if career is None or career.pending_demo is None:
            if career is not None and career.pending_letter is not None:
                return CompleteSprintResult(
                    ok=True,
                    status="letter",
                    forced=career.pending_forced,
                    letter=career.pending_letter,
                )
            return CompleteSprintResult(error="no_demo", message="Пятничного демо нет")
        addresses = None
        criterion = career.pending_demo.criterion
        if criterion and self.career_llm is not None:
            try:
                addresses = await self.career_llm.grade_demo_answer(criterion, answer)
            except Exception:
                _logger.exception("friday demo grade failed user_id=%s", user_id)
                addresses = None
            if addresses is None:
                _logger.warning(
                    "friday demo graded by length, model unavailable user_id=%s",
                    user_id,
                )
        held, error = score_friday_demo(pitch, answer, addresses=addresses)
        if error == "empty":
            return CompleteSprintResult(
                error="empty",
                message="Напиши питч и ответ на вопрос Сары.",
            )
        incident = incident_outcome(tasks)
        letter = draft_sprint_letter(
            career,
            [(task.title, task.close_quality) for task in graded_tasks(tasks)],
            trajectory_blocked=career.pending_demo.trajectory_blocked,
            demo_held=held,
            incident=incident,
        )
        progress = apply_demo(career.progress, held=held, incident=incident)
        badges, unlocked = award(progress, career.badges)
        career = replace(
            career,
            pending_letter=letter,
            pending_demo=None,
            progress=progress,
            badges=badges,
        )
        if not await self.career_db.save(career):
            return CompleteSprintResult(error="update_failed", message="Не удалось сохранить письмо")
        return CompleteSprintResult(
            ok=True,
            status="letter",
            forced=career.pending_forced,
            letter=letter,
            unlocked=unlocked,
        )

    async def _open_demo(
            self,
            tasks: list[TaskDTO],
            authorization: str | None,
            trajectory_blocked: bool,
    ) -> FridayDemo:
        criterion = await self._weak_tail(tasks, authorization)
        return build_friday_demo(criterion, trajectory_blocked=trajectory_blocked)

    async def accept(
            self,
            user_id: int,
            authorization: str | None = None,
    ) -> CompleteSprintResult:
        career = await self.career_db.get(user_id)
        if career is None or career.pending_letter is None:
            return CompleteSprintResult(error="no_letter", message="Письма нет")

        active_project = await self.user_project_db.get_active_user_project(user_id)
        active_sprint = await self.sprint_db.get_current_sprint(user_id)
        if active_project is None or active_sprint is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")
        tasks = await self.task_db.get_tasks(active_sprint.sprint_id, user_id)
        if tasks is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")
        if not required_tasks_done(tasks):
            return CompleteSprintResult(
                error="tasks_open",
                message=incomplete_sprint_message(tasks),
            )

        applied = accept_letter(career)
        if applied is None or not await self.career_db.save(applied):
            return CompleteSprintResult(error="update_failed", message="Не удалось принять письмо")
        had = {badge.id for badge in career.badges}
        unlocked = tuple(badge.id for badge in applied.badges if badge.id not in had)

        result = await self._open_next(
            user_id=user_id,
            authorization=authorization,
            force=career.pending_forced,
            active_project=active_project,
            active_sprint=active_sprint,
            tasks=tasks,
        )
        if not result.ok:
            await self.career_db.save(career)
            return result
        return replace(result, unlocked=unlocked)

    async def _open_next(
            self,
            user_id: int,
            authorization: str | None,
            force: bool,
            active_project: Any,
            active_sprint: Any,
            tasks: list[TaskDTO],
    ) -> CompleteSprintResult:
        graded = graded_tasks(tasks)
        anchor_task_id = graded[-1].task_id if graded else None
        hint = await self.trajectory_gateway.get_trajectory(
            authorization or "",
            task_id=anchor_task_id,
        )
        decision = evaluate_sprint_hold(graded, hint)
        template = await self.project_db.get_template_by_id(active_project.template_id)
        if template is None:
            return CompleteSprintResult(error="not_found", message="Не найдено")
        next_sprint_template = next(
            (s for s in template.sprints if s.order == active_sprint.order + 1),
            None,
        )
        if next_sprint_template is not None and not next_sprint_template.tasks:
            return CompleteSprintResult(
                error="empty_next_sprint",
                message="Шаблон следующего спринта без задач — спринт не закрыт.",
            )

        close_mode = "forced" if force or decision.hold else "ok"
        now = datetime.datetime.now()
        closed_sprint_id = active_sprint.sprint_id
        update_sprint = await self.sprint_db.update_sprint(
            user_id=user_id,
            old_status="active",
            new_status=self.SPRINT_COMPLETED,
            completed_at=now,
            close_mode=close_mode,
            sprint_id=closed_sprint_id,
        )
        if not update_sprint:
            return CompleteSprintResult(error="update_failed", message="Не удалось закрыть спринт")

        next_sprint_id: int | None = None
        published_tasks: list[tuple[int, str]] = []
        try:
            if next_sprint_template is None:
                update_user_project = await self.user_project_db.update_user_project(
                    user_project_id=active_project.user_project_id,
                    new_status=self.PROJECT_COMPLETED,
                    completed_at=now,
                )
                if not update_user_project:
                    raise RuntimeError("failed to complete project")
                return CompleteSprintResult(
                    ok=True,
                    status=self.PROJECT_FINISHED,
                    forced=close_mode == "forced",
                )

            next_sprint_id = self._generate_id()
            new_sprint = SprintDTO(
                sprint_id=next_sprint_id,
                user_project_id=active_project.user_project_id,
                user_id=user_id,
                order=next_sprint_template.order,
                status="active",
                started_at=now,
                completed_at=None,
            )
            created = await self.sprint_db.create_sprint(new_sprint)
            if not created:
                raise RuntimeError("failed to create next sprint")

            created_tasks: list[TaskDTO] = []
            tail = await self._weak_tail(tasks, authorization)
            for index, template_task in enumerate(next_sprint_template.tasks):
                description = template_task.description
                if index == 0 and tail:
                    description = append_weak_tail(description, tail)
                new_task = TaskDTO(
                    task_id=self._generate_id(),
                    user_id=user_id,
                    user_project_id=active_project.user_project_id,
                    sprint_id=next_sprint_id,
                    title=template_task.title,
                    description=description,
                    status="todo",
                    created_at=now,
                    completed_at=None,
                )
                task_created = await self.task_db.create_task(new_task)
                if not task_created:
                    raise RuntimeError("failed to create next sprint tasks")
                created_tasks.append(new_task)

            career_now = await self.career_db.get(user_id)
            extra = await compose_peer_review(
                None if career_now is None else career_now.grade,
                self.career_llm,
            )
            if extra is not None and not any(task.title == PEER_REVIEW_TITLE for task in created_tasks):
                title, description, review_bug = extra
                review_task = TaskDTO(
                    task_id=self._generate_id(),
                    user_id=user_id,
                    user_project_id=active_project.user_project_id,
                    sprint_id=next_sprint_id,
                    title=title,
                    description=description,
                    status="todo",
                    created_at=now,
                    completed_at=None,
                    review_bug=review_bug,
                )
                task_created = await self.task_db.create_task(review_task)
                if not task_created:
                    raise RuntimeError("failed to create peer review task")
                created_tasks.append(review_task)

            for new_task in created_tasks:
                await self.task_event_producer.produce_task_created(
                    task_id=new_task.task_id,
                    user_id=user_id,
                    status=new_task.status,
                    task_description=new_task.description,
                )
                published_tasks.append((new_task.task_id, new_task.description))

            new_order = active_project.current_sprint_order + 1
            order_updated = await self.user_project_db.update_current_sprint_order(
                user_project_id=active_project.user_project_id,
                new_sprint_order=new_order,
            )
            if not order_updated:
                raise RuntimeError("failed to bump sprint order")

            return CompleteSprintResult(
                ok=True,
                status=self.NEW_PROJECT,
                forced=close_mode == "forced",
            )
        except Exception:
            _logger.exception(
                "complete_sprint rolled back user_id=%s after partial failure",
                user_id,
            )
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
                        "complete_sprint could not emit cancel for task_id=%s",
                        task_id,
                    )
            if next_sprint_id is not None:
                deleted = await self.task_db.delete_tasks_by_sprint(next_sprint_id, user_id)
                if not deleted:
                    _logger.error(
                        "complete_sprint could not delete orphan tasks "
                        "user_id=%s sprint_id=%s",
                        user_id,
                        next_sprint_id,
                    )
                cancelled = await self.sprint_db.update_sprint(
                    user_id=user_id,
                    old_status="active",
                    new_status="cancelled",
                    completed_at=None,
                    close_mode=None,
                    sprint_id=next_sprint_id,
                )
                if not cancelled:
                    _logger.error(
                        "complete_sprint could not cancel partial next sprint "
                        "user_id=%s sprint_id=%s — refusing reopen to avoid two actives",
                        user_id,
                        next_sprint_id,
                    )
                    return CompleteSprintResult(
                        error="update_failed",
                        message=(
                            "Не удалось откатить новый спринт — "
                            "активный спринт не восстановлен автоматически"
                        ),
                    )
                if not deleted:
                    return CompleteSprintResult(
                        error="update_failed",
                        message=(
                            "Не удалось удалить задачи нового спринта при откате — "
                            "проверьте данные вручную"
                        ),
                    )
            reopened = await self.sprint_db.update_sprint(
                user_id=user_id,
                old_status=self.SPRINT_COMPLETED,
                new_status="active",
                completed_at=None,
                close_mode=None,
                sprint_id=closed_sprint_id,
            )
            if not reopened:
                _logger.error(
                    "complete_sprint could not reopen sprint user_id=%s sprint_id=%s",
                    user_id,
                    closed_sprint_id,
                )
                return CompleteSprintResult(
                    error="update_failed",
                    message=(
                        "Не удалось завершить спринт атомарно — "
                        "активный спринт не восстановлен"
                    ),
                )
            return CompleteSprintResult(
                error="update_failed",
                message="Не удалось завершить спринт атомарно — активный спринт восстановлен",
            )

    async def _weak_tail(
            self,
            tasks: list[TaskDTO],
            authorization: str | None,
    ) -> str | None:
        weak = [
            task for task in graded_tasks(tasks)
            if (task.close_quality or "") == "weak" and not is_peer_review_task(task.title)
        ]
        if not weak or self.review_gateway is None:
            return None
        latest_weak = weak[-1]
        try:
            snapshots = await self.review_gateway.get_task_reviews(
                latest_weak.task_id,
                authorization or "",
            )
        except Exception:
            _logger.exception(
                "weak tail reviews failed task_id=%s",
                latest_weak.task_id,
            )
            return None
        return failed_criterion_from_latest(snapshots)

    @staticmethod
    def _generate_id() -> int:
        return uuid.uuid4().int % (2**53)
