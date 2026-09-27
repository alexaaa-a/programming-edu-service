import datetime
import logging
from dataclasses import dataclass

from task_service.app.application.interfaces.career_llm import CareerLlmInterface
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.application.night_incident import open_night_incident
from task_service.app.application.peer_review import is_peer_review_task, judge_peer_note

_logger = logging.getLogger("task_service.submit_peer_review")

_OPEN = frozenset({"todo", "in_progress", "review"})


@dataclass(frozen=True, slots=True)
class SubmitPeerReviewResult:
    ok: bool = False
    error: str | None = None
    message: str | None = None
    close_quality: str | None = None
    emma: str | None = None


class SubmitPeerReviewUseCase:
    def __init__(
            self,
            task_db: TaskDBInterface,
            task_event_producer: TaskEventProducerInterface,
            career_db: CareerDBInterface = None,  # type: ignore[assignment]
            career_llm: CareerLlmInterface = None,  # type: ignore[assignment]
    ) -> None:
        self.task_db = task_db
        self.task_event_producer = task_event_producer
        self.career_db = career_db
        self.career_llm = career_llm

    async def __call__(self, user_id: int, task_id: int, note: str) -> SubmitPeerReviewResult:
        text = note.strip()
        if not text:
            return SubmitPeerReviewResult(error="empty", message="Напиши, что не так в коде стажёра.")
        task = await self.task_db.get_task_by_id(task_id, user_id)
        if task is None:
            return SubmitPeerReviewResult(error="not_found", message="Задача не найдена")
        if not is_peer_review_task(task.title):
            return SubmitPeerReviewResult(
                error="not_peer",
                message="Это не ревью стажёра.",
            )
        if task.status == "done":
            return SubmitPeerReviewResult(error="already_done", message="Эмма уже закрыла это ревью.")
        if task.status not in _OPEN:
            return SubmitPeerReviewResult(error="not_peer", message="Задачу сейчас нельзя отдать Эмме.")

        judged = await judge_peer_note(text, task.description, task.review_bug, self.career_llm)
        if judged is None:
            return SubmitPeerReviewResult(
                error="unread",
                message="Эмма не дочитала заметку. Отправь ещё раз.",
            )
        found, line = judged
        quality = "ok" if found else "weak"
        previous_status = task.status
        previous_completed_at = task.completed_at
        previous_quality = task.close_quality
        previous_note = task.close_note
        completed_at = datetime.datetime.now()
        updated = await self.task_db.update_task(
            task_id=task_id,
            new_status="done",
            completed_at=completed_at,
            close_quality=quality,
            user_id=user_id,
            close_note=line,
        )
        if not updated:
            return SubmitPeerReviewResult(error="update_failed", message="Не удалось закрыть ревью")
        try:
            await self.task_event_producer.produce_task_status_updated(
                task_id=task_id,
                user_id=user_id,
                status="done",
                task_description=task.description,
            )
        except Exception:
            _logger.exception("peer review produce failed task_id=%s", task_id)
            await self.task_db.update_task(
                task_id=task_id,
                new_status=previous_status,
                completed_at=previous_completed_at,
                close_quality=previous_quality,
                user_id=user_id,
                close_note=previous_note or "",
            )
            return SubmitPeerReviewResult(
                error="produce_failed",
                message="Не удалось отправить событие статуса. Попробуйте ещё раз.",
            )
        if quality == "ok":
            await open_night_incident(
                task_db=self.task_db,
                career_db=self.career_db,
                producer=self.task_event_producer,
                user_id=user_id,
                closed=task,
                quality=quality,
                career_llm=self.career_llm,
            )
        return SubmitPeerReviewResult(ok=True, close_quality=quality, emma=line)
