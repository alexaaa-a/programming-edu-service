import datetime
import logging
from dataclasses import dataclass, replace
from typing import Any

from task_service.app.application.career import local_round_limit, new_intern
from task_service.app.application.close_gate import normalize_score
from task_service.app.application.quests import apply_close, award
from task_service.app.config import Settings
from task_service.app.application.night_incident import open_night_incident
from task_service.app.application.peer_review import is_peer_review_task
from task_service.app.application.close_gate import evaluate_close
from task_service.app.application.interfaces.career_llm import CareerLlmInterface
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.application.interfaces.review_gateway import TaskReviewGatewayInterface

_logger = logging.getLogger("task_service.update_task_status")


@dataclass(frozen=True, slots=True)
class UpdateTaskStatusResult:
    ok: bool = False
    error: str | None = None
    message: str | None = None
    close_quality: str | None = None
    unlocked: tuple[str, ...] = ()


class UpdateTaskStatusUseCase:
    ALLOWED_TRANSITIONS = {
        "todo": ["in_progress"],
        "in_progress": ["review"],
        "review": ["done"],
    }
    FINISH_STATUS = "done"

    def __init__(
        self,
        task_db: TaskDBInterface,
        task_event_producer: TaskEventProducerInterface,
        review_gateway: TaskReviewGatewayInterface,
        settings: Settings = None,  # type: ignore[assignment]
        career_db: CareerDBInterface = None,  # type: ignore[assignment]
        career_llm: CareerLlmInterface = None,  # type: ignore[assignment]
    ) -> None:
        self.task_db = task_db
        self.task_event_producer = task_event_producer
        self.review_gateway = review_gateway
        self.career_db = career_db
        self.career_llm = career_llm
        close = getattr(settings, "close_gate_settings", None)
        self._pass_score = int(getattr(close, "pass_score", 8))
        self._max_rounds = max(1, int(getattr(close, "max_rounds", 2)))

    async def __call__(
            self,
            user_id: int,
            task_id: int,
            new_status: str,
            authorization: str | None = None,
    ) -> UpdateTaskStatusResult:
        task = await self.task_db.get_task_by_id(task_id, user_id)
        if task is None:
            return UpdateTaskStatusResult(
                error="not_found",
                message="Задача не найдена или переход в данный статус невозможен",
            )

        if is_peer_review_task(task.title) and new_status != "in_progress":
            return UpdateTaskStatusResult(
                error="bad_transition",
                message="Эту задачу закрывает заметка для Эммы, не сдача кода.",
            )

        allow_or_not = self.ALLOWED_TRANSITIONS.get(task.status)
        if not allow_or_not:
            return UpdateTaskStatusResult(
                error="not_found",
                message="Задача не найдена или переход в данный статус невозможен",
            )

        if new_status not in allow_or_not:
            return UpdateTaskStatusResult(
                error="bad_transition",
                message="Недопустимый переход статуса (todo→in_progress→review→done)",
            )

        previous_status = task.status
        previous_completed_at = task.completed_at
        previous_close_quality = task.close_quality

        completed_at = None
        close_quality = None
        best_score: float | None = None
        attempts = 0
        if new_status == self.FINISH_STATUS:
            closing, error = await self._close_gate(task_id, user_id, authorization)
            if error is not None:
                return error
            decision, best_score, attempts = closing
            close_quality = decision.quality
            completed_at = datetime.datetime.now()

        update = await self.task_db.update_task(
            task_id=task_id,
            new_status=new_status,
            completed_at=completed_at,
            close_quality=close_quality,
            user_id=user_id,
        )
        if not update:
            return UpdateTaskStatusResult(
                error="update_failed",
                message="Не удалось обновить статус",
            )

        try:
            await self.task_event_producer.produce_task_status_updated(
                task_id=task_id,
                user_id=user_id,
                status=new_status,
                task_description=task.description,
                round_limit=await self._round_limit(user_id, task_id),
            )
        except Exception:
            _logger.exception(
                "task status produce failed — rolling back task_id=%s user_id=%s",
                task_id,
                user_id,
            )
            rolled = await self.task_db.update_task(
                task_id=task_id,
                new_status=previous_status,
                completed_at=previous_completed_at,
                close_quality=previous_close_quality,
                user_id=user_id,
            )
            if not rolled:
                _logger.error(
                    "task status rollback failed task_id=%s user_id=%s",
                    task_id,
                    user_id,
                )
            return UpdateTaskStatusResult(
                error="produce_failed",
                message="Не удалось отправить событие статуса. Попробуйте ещё раз.",
            )
        if new_status == self.FINISH_STATUS and close_quality == "ok":
            await open_night_incident(
                task_db=self.task_db,
                career_db=self.career_db,
                producer=self.task_event_producer,
                user_id=user_id,
                closed=task,
                quality=close_quality,
                career_llm=self.career_llm,
            )
        unlocked: tuple[str, ...] = ()
        if new_status == self.FINISH_STATUS:
            unlocked = await self._record_close(
                user_id=user_id,
                quality=close_quality,
                score=best_score,
                attempts=attempts,
            )
        return UpdateTaskStatusResult(
            ok=True,
            close_quality=close_quality,
            unlocked=unlocked,
        )

    async def _record_close(
            self,
            user_id: int,
            quality: str | None,
            score: float | None,
            attempts: int,
    ) -> tuple[str, ...]:
        """Счётчики и бейджи за закрытие. Сбой здесь не отменяет закрытие."""
        if self.career_db is None:
            return ()
        try:
            career = await self.career_db.get(user_id) or new_intern(user_id)
            progress = apply_close(
                career.progress,
                quality=quality,
                score=score,
                attempts=attempts,
            )
            badges, unlocked = award(progress, career.badges)
            saved = await self.career_db.save(
                replace(career, progress=progress, badges=badges)
            )
            return unlocked if saved else ()
        except Exception:
            _logger.exception("close progress failed user_id=%s", user_id)
            return ()

    async def _round_limit(self, user_id: int, task_id: int) -> int:
        if self.career_db is None:
            return self._max_rounds
        career = await self.career_db.get(user_id)
        return local_round_limit(career, task_id, base=self._max_rounds)

    async def _close_gate(
            self,
            task_id: int,
            user_id: int,
            authorization: str | None,
    ) -> tuple[Any, UpdateTaskStatusResult | None]:
        """Решение о закрытии плюс лучший балл и число сдач — для бейджей."""
        snapshots = await self.review_gateway.get_task_reviews(
            task_id,
            authorization or "",
        )
        if snapshots is None:
            return None, UpdateTaskStatusResult(
                error="close_unavailable",
                message="Не удалось проверить ревью. Попробуй закрыть задачу чуть позже.",
            )
        decision = evaluate_close(
            snapshots,
            pass_score=self._pass_score,
            max_rounds=await self._round_limit(user_id, task_id),
        )
        if not decision.allowed:
            return None, UpdateTaskStatusResult(
                error="close_blocked",
                message=decision.reason,
            )
        scores = [
            normalize_score(item.score)
            for item in snapshots
            if getattr(item, "score", None) is not None
        ]
        best = max(scores) if scores else None
        return (decision, best, len(scores)), None
