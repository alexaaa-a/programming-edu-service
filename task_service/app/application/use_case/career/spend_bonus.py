from dataclasses import dataclass

from task_service.app.application.career import (
    CareerState,
    consume_emma_session,
    local_round_limit,
    spend_bonus,
)
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface


@dataclass(frozen=True, slots=True)
class SpendBonusResult:
    state: CareerState | None = None
    error: str | None = None


class SpendBonusUseCase:
    def __init__(
            self,
            career_db: CareerDBInterface,
            task_db: TaskDBInterface,
            task_event_producer: TaskEventProducerInterface,
    ) -> None:
        self._career_db = career_db
        self._task_db = task_db
        self._task_event_producer = task_event_producer

    async def __call__(
            self,
            user_id: int,
            item: str,
            task_id: int | None = None,
    ) -> SpendBonusResult:
        state = await self._career_db.get(user_id)
        if state is None:
            return SpendBonusResult(error="not_found")
        next_state, error = spend_bonus(state, item, task_id=task_id)
        if error or next_state is None:
            return SpendBonusResult(error=error or "spend_failed")
        saved = await self._career_db.save(next_state)
        if not saved:
            return SpendBonusResult(error="save_failed")
        if item == "extra_round" and task_id is not None:
            await self._publish_round_limit(user_id, task_id, next_state)
        return SpendBonusResult(state=next_state)

    async def consume_emma(self, user_id: int) -> SpendBonusResult:
        state = await self._career_db.get(user_id)
        if state is None:
            return SpendBonusResult(error="not_found")
        next_state, error = consume_emma_session(state)
        if error or next_state is None:
            return SpendBonusResult(error=error or "nothing_to_use")
        saved = await self._career_db.save(next_state)
        if not saved:
            return SpendBonusResult(error="save_failed")
        return SpendBonusResult(state=next_state)

    async def _publish_round_limit(self, user_id: int, task_id: int, state: CareerState) -> None:
        task = await self._task_db.get_task_by_id(task_id, user_id)
        if task is None:
            return
        try:
            await self._task_event_producer.produce_task_status_updated(
                task_id=task.task_id,
                user_id=user_id,
                status=task.status,
                task_description=task.description,
                round_limit=local_round_limit(state, task_id),
            )
        except Exception:
            return
