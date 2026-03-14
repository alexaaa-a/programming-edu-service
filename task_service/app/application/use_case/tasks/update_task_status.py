import datetime

from task_service.app.application.interfaces.db.task_db import TaskDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface


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
    ) -> None:
        self.task_db = task_db
        self.task_event_producer = task_event_producer

    async def __call__(self, user_id: int, task_id: int, new_status: str) -> bool | None:
        task = await self.task_db.get_task_by_id(task_id, user_id)
        if task is None:
            return None

        allow_or_not = self.ALLOWED_TRANSITIONS.get(task.status)
        if not allow_or_not:
            return None

        if new_status not in allow_or_not:
            return False

        completed_at = None
        if new_status == self.FINISH_STATUS:
            completed_at = datetime.datetime.now()

        update = await self.task_db.update_task(
            task_id=task_id,
            new_status=new_status,
            completed_at=completed_at,
        )
        if update:
            await self.task_event_producer.produce_task_status_updated(
                task_id=task_id,
                user_id=user_id,
                status=new_status,
            )
        return update
