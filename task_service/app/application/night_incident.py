import datetime
import logging
import uuid
from typing import Protocol

from task_service.app.application.career import INCIDENT_BONUS, mark_incident_used
from task_service.app.application.dto.task import TaskDTO

_logger = logging.getLogger("task_service.night_incident")

NIGHT_INCIDENT_TITLE = "Ночной инцидент"
def incident_description(scene: str, code: str, expect: str) -> str:
    return f"""Ночь. Эмма пишет: {scene.strip()}

{code.strip()}

Почини: {expect.strip()}

На доске
Пока задача в «к выполнению», спринт можно закрыть без неё. Если взял в работу — доведи до закрытия. Полный зачёт даёт в письме разовую премию {INCIDENT_BONUS}. Слабое закрытие и молчание премию не дают, оклад тот же.
"""


NIGHT_INCIDENT_DESCRIPTION = f"""Ночь. Эмма пишет: на проде 500.

Ручка скидки делит цену на процент. Ноль в проценте роняет сервис.

def discounted(price: int, percent: int) -> int:
    return price // percent

Почини падение при percent == 0. Для ненулевого percent оставь price // percent.

На доске
Пока задача в «к выполнению», спринт можно закрыть без неё. Если взял в работу — доведи до закрытия. Полный зачёт даёт в письме разовую премию {INCIDENT_BONUS}. Слабое закрытие и молчание премию не дают, оклад тот же.
"""


class _Task(Protocol):
    title: str
    status: str
    close_quality: str | None


def is_night_incident(title: str) -> bool:
    return title.strip() == NIGHT_INCIDENT_TITLE


def required_tasks_done(tasks: list[_Task]) -> bool:
    for task in tasks:
        if task.status == "done":
            continue
        if is_night_incident(task.title) and task.status in {"todo", "cancelled"}:
            continue
        return False
    return True


def incomplete_sprint_message(tasks: list[_Task]) -> str:
    real_open = [
        task for task in tasks
        if task.status != "done" and not is_night_incident(task.title)
    ]
    started = [
        task for task in tasks
        if is_night_incident(task.title) and task.status in {"in_progress", "review"}
    ]
    if started and not real_open:
        return (
            "Ночной инцидент уже в работе. Закрой его: "
            "слабый зачёт спринт отпускает, премию даёт только полный."
        )
    return "Не все задачи спринта выполнены"


def graded_tasks(tasks: list) -> list:
    return [task for task in tasks if not is_night_incident(task.title)]


def incident_outcome(tasks: list[_Task]) -> str | None:
    incidents = [
        task for task in tasks
        if is_night_incident(task.title) and task.status != "cancelled"
    ]
    if not incidents:
        return None
    if any(task.status in {"todo", "in_progress", "review"} for task in incidents):
        return "skipped"
    if all((getattr(task, "close_quality", None) or "") == "ok" for task in incidents):
        return "done"
    return "weak"


async def compose_night_incident(career_llm) -> str:
    if career_llm is not None:
        try:
            drafted = await career_llm.generate_night_incident()
        except Exception:
            _logger.exception("night incident generation failed")
            drafted = None
        if drafted is not None:
            return incident_description(drafted.scene, drafted.code, drafted.expect)
    return NIGHT_INCIDENT_DESCRIPTION


async def open_night_incident(
        task_db,
        career_db,
        producer,
        user_id: int,
        closed: TaskDTO,
        quality: str | None,
        career_llm=None,
) -> None:
    if career_db is None or quality != "ok":
        return
    if is_night_incident(closed.title):
        return
    career = await career_db.get(user_id)
    if career is None or career.incident_used:
        return
    existing = await task_db.get_tasks(closed.sprint_id, user_id) or []
    if any(is_night_incident(task.title) and task.status != "cancelled" for task in existing):
        await career_db.save(mark_incident_used(career))
        return
    now = datetime.datetime.now()
    task = TaskDTO(
        task_id=uuid.uuid4().int % (2**53),
        user_id=user_id,
        user_project_id=closed.user_project_id,
        sprint_id=closed.sprint_id,
        title=NIGHT_INCIDENT_TITLE,
        description=await compose_night_incident(career_llm),
        status="todo",
        created_at=now,
        completed_at=None,
    )
    if not await task_db.create_task(task):
        return
    try:
        await producer.produce_task_created(
            task_id=task.task_id,
            user_id=user_id,
            status=task.status,
            task_description=task.description,
        )
    except Exception:
        _logger.exception("night incident publish failed task_id=%s", task.task_id)
        await task_db.update_task(
            task_id=task.task_id,
            new_status="cancelled",
            user_id=user_id,
        )
        return
    await career_db.save(mark_incident_used(career))
