import asyncio
from datetime import datetime
from types import SimpleNamespace

from task_service.app.application.close_gate import ReviewSnapshot
from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.use_case.tasks.update_task_status import (
    UpdateTaskStatusUseCase,
)


class FakeTaskDB:
    def __init__(self, task: TaskDTO | None) -> None:
        self.task = task
        self.updates: list[dict] = []

    async def get_task_by_id(self, task_id: int, user_id: int) -> TaskDTO | None:
        if self.task is None:
            return None
        if self.task.task_id != task_id or self.task.user_id != user_id:
            return None
        return self.task

    async def update_task(self, task_id: int, new_status: str, completed_at=None, close_quality=None, user_id=None) -> bool:
        self.updates.append(
            {
                "task_id": task_id,
                "user_id": user_id,
                "new_status": new_status,
                "completed_at": completed_at,
                "close_quality": close_quality,
            }
        )
        if self.task is not None:
            self.task.status = new_status
            self.task.completed_at = completed_at
            self.task.close_quality = close_quality
        return True


class FakeProducer:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def produce_task_status_updated(self, **kwargs) -> None:
        self.events.append(kwargs)


class FakeGateway:
    def __init__(self, snapshots: list[ReviewSnapshot] | None) -> None:
        self.snapshots = snapshots
        self.calls: list[tuple[int, str]] = []

    async def get_task_reviews(self, task_id: int, authorization: str):
        self.calls.append((task_id, authorization))
        return self.snapshots


def _task(status: str = "review") -> TaskDTO:
    return TaskDTO(
        task_id=11,
        user_id=7,
        user_project_id=1,
        sprint_id=2,
        title="Сумма",
        description="сложи числа",
        status=status,
        created_at=datetime.now(),
        completed_at=None,
    )


def _uc(task: TaskDTO | None, snapshots: list[ReviewSnapshot] | None) -> tuple[UpdateTaskStatusUseCase, FakeTaskDB, FakeGateway, FakeProducer]:
    db = FakeTaskDB(task)
    gateway = FakeGateway(snapshots)
    producer = FakeProducer()
    uc = UpdateTaskStatusUseCase(
        task_db=db,
        task_event_producer=producer,
        review_gateway=gateway,
        settings=SimpleNamespace(close_gate_settings=SimpleNamespace(pass_score=8, max_rounds=2)),
    )
    return uc, db, gateway, producer


def test_not_found():
    uc, *_ = _uc(None, [])
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer t"))
    assert result.error == "not_found"


def test_bad_transition():
    uc, *_ = _uc(_task("todo"), [])
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer t"))
    assert result.error == "bad_transition"


def test_todo_to_in_progress_skips_gateway():
    uc, db, gateway, producer = _uc(_task("todo"), None)
    result = asyncio.run(uc(7, 11, "in_progress", authorization="Bearer t"))
    assert result.ok is True
    assert gateway.calls == []
    assert db.updates[0]["close_quality"] is None
    assert producer.events[0]["status"] == "in_progress"


def test_blocks_weak_first_review():
    uc, db, gateway, _ = _uc(_task("review"), [ReviewSnapshot(status="reviewed", score=5)])
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer abc"))
    assert result.error == "close_blocked"
    assert "Балл ниже 8" in (result.message or "")
    assert db.updates == []
    assert gateway.calls == [(11, "Bearer abc")]


def test_bought_round_blocks_weak_close_until_the_third_attempt():
    from task_service.app.application.career import CareerPurchase, CareerState, new_intern

    intern = new_intern(7)
    bought = CareerState(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        purchases=(
            CareerPurchase(item="extra_round", price=15_000, at=intern.created_at, task_id=11),
        ),
        created_at=intern.created_at,
    )

    class CareerDB:
        async def get(self, user_id: int):
            return bought

        async def save(self, state) -> bool:
            return True

        async def delete(self, user_id: int) -> bool:
            return True

    task = _task("review")
    db = FakeTaskDB(task)
    uc = UpdateTaskStatusUseCase(
        task_db=db,
        task_event_producer=FakeProducer(),
        review_gateway=FakeGateway(
            [
                ReviewSnapshot(status="reviewed", score=4),
                ReviewSnapshot(status="reviewed", score=6),
            ]
        ),
        settings=SimpleNamespace(close_gate_settings=SimpleNamespace(pass_score=8, max_rounds=2)),
        career_db=CareerDB(),
    )
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer t"))
    assert result.error == "close_blocked"
    assert db.updates == []


def test_allows_weak_after_two_attempts():
    uc, db, _, _ = _uc(
        _task("review"),
        [
            ReviewSnapshot(status="reviewed", score=4),
            ReviewSnapshot(status="reviewed", score=6),
        ],
    )
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer t"))
    assert result.ok is True
    assert result.close_quality == "weak"
    assert db.updates[0]["close_quality"] == "weak"
    assert db.updates[0]["completed_at"] is not None


def test_allows_ok_on_pass_score():
    uc, db, _, _ = _uc(_task("review"), [ReviewSnapshot(status="reviewed", score=9)])
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer t"))
    assert result.ok is True
    assert result.close_quality == "ok"
    assert db.updates[0]["close_quality"] == "ok"


def test_unavailable_reviews_block_close():
    uc, db, _, _ = _uc(_task("review"), None)
    result = asyncio.run(uc(7, 11, "done", authorization="Bearer t"))
    assert result.error == "close_unavailable"
    assert db.updates == []


def test_produce_failure_rolls_back_status():
    class BoomProducer:
        async def produce_task_status_updated(self, **kwargs) -> None:
            raise RuntimeError("kafka down")

    task = _task("todo")
    db = FakeTaskDB(task)
    uc = UpdateTaskStatusUseCase(
        task_db=db,
        task_event_producer=BoomProducer(),  # type: ignore[arg-type]
        review_gateway=FakeGateway([]),
        settings=SimpleNamespace(close_gate_settings=SimpleNamespace(pass_score=8, max_rounds=2)),
    )
    result = asyncio.run(uc(7, 11, "in_progress", authorization="Bearer t"))
    assert result.error == "produce_failed"
    assert len(db.updates) == 2
    assert db.updates[0]["new_status"] == "in_progress"
    assert db.updates[1]["new_status"] == "todo"
    assert db.updates[1]["user_id"] == 7
    assert task.status == "todo"


def test_task_db_update_requires_user_id_filter():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "app/infrastructure/mongo/task_db.py"
    ).read_text(encoding="utf-8")
    assert 'query["user_id"] = user_id' in text or '"user_id": user_id' in text
