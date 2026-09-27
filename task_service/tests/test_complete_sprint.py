import asyncio
from datetime import datetime
from types import SimpleNamespace

from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.review_gateway import TrajectoryHint
from task_service.app.application.sprint_hold import evaluate_sprint_hold
from task_service.app.application.use_case.sprint.complete_sprint import CompleteSprintUseCase


class FakeTasks:
    def __init__(self, tasks: list[TaskDTO]) -> None:
        self.tasks = tasks
        self.deleted_sprints: list[tuple[int, int]] = []

    async def get_tasks(self, sprint_id: int, user_id: int):
        return self.tasks

    async def delete_tasks_by_sprint(self, sprint_id: int, user_id: int) -> bool:
        self.deleted_sprints.append((sprint_id, user_id))
        return True


class FakeSprintDB:
    async def get_current_sprint(self, user_id: int):
        return SimpleNamespace(sprint_id=2, order=1)

    async def update_sprint(self, **kwargs):
        raise AssertionError("sprint should not complete on hold")


class RecordingSprint(FakeSprintDB):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def update_sprint(self, **kwargs):
        self.calls.append(kwargs)
        return True


class FakeProjectDB:
    async def get_active_user_project(self, user_id: int):
        return SimpleNamespace(user_project_id=1, template_id=9, current_sprint_order=1)

    async def update_user_project(self, **kwargs):
        return True

    async def update_current_sprint_order(self, **kwargs):
        return True


class FakeTemplates:
    async def get_template_by_id(self, template_id: int):
        return SimpleNamespace(sprints=[])


class FakeProducer:
    async def produce_task_created(self, **kwargs) -> None:
        return None

    async def produce_task_status_updated(self, **kwargs) -> None:
        return None


class FakeCareerDB:
    def __init__(self) -> None:
        self.state = None

    async def get(self, user_id: int):
        return self.state

    async def save(self, state) -> bool:
        self.state = state
        return True


class FakeTrajectory:
    def __init__(self, hint: TrajectoryHint | None) -> None:
        self.hint = hint
        self.calls = 0
        self.task_ids: list[int | None] = []

    async def get_trajectory(self, authorization: str, task_id: int | None = None):
        self.calls += 1
        self.task_ids.append(task_id)
        return self.hint


def _done(**kwargs) -> TaskDTO:
    return TaskDTO(
        task_id=kwargs.get("task_id", 1),
        user_id=7,
        user_project_id=1,
        sprint_id=2,
        title="t",
        description="d",
        status=kwargs.get("status", "done"),
        created_at=datetime.now(),
        completed_at=datetime.now(),
        close_quality=kwargs.get("close_quality"),
    )


def _uc(
    tasks: list[TaskDTO],
    hint: TrajectoryHint | None,
    sprint_db: FakeSprintDB | None = None,
) -> tuple[CompleteSprintUseCase, FakeTrajectory, FakeSprintDB]:
    gateway = FakeTrajectory(hint)
    db = sprint_db or FakeSprintDB()
    uc = CompleteSprintUseCase(
        task_db=FakeTasks(tasks),
        sprint_db=db,
        user_project_db=FakeProjectDB(),
        project_db=FakeTemplates(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=gateway,
        career_db=FakeCareerDB(),
    )
    return uc, gateway, db


_PITCH = "Собрали поиск по заказам. Клиент находит позицию за один запрос."
_ANSWER = "Критерий закрыли тестом и повторным ревью."


def _held(uc: CompleteSprintUseCase, user_id: int = 7):
    return asyncio.run(
        uc.submit_demo(user_id, pitch=_PITCH, answer=_ANSWER)
    )


def test_open_tasks_block_complete():
    uc, gateway, _ = _uc([_done(status="review")], TrajectoryHint("next_sprint", "ok", False))
    result = asyncio.run(uc(7, authorization="Bearer t"))
    assert result.error == "tasks_open"
    assert gateway.calls == 0


def test_heavy_trajectory_does_not_block_sprint_complete():
    uc, gateway, _ = _uc(
        [_done(close_quality="ok")],
        TrajectoryHint("hold_sprint", "Траектория ещё тяжёлая.", True),
    )
    result = asyncio.run(uc(7, authorization="Bearer t"))
    assert result.ok is True
    assert result.status == "demo"
    assert result.demo is not None and result.demo.trajectory_blocked is True
    assert gateway.calls == 1
    assert gateway.task_ids == [1]


def test_complete_passes_done_task_id_to_trajectory():
    sprint_db = RecordingSprint()
    uc, gateway, _ = _uc(
        [_done(task_id=42, close_quality="ok")],
        TrajectoryHint("next_sprint", "ok", False),
        sprint_db=sprint_db,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t"))
    assert draft.status == "demo"
    assert sprint_db.calls == []
    assert gateway.task_ids == [42]
    assert _held(uc).status == "letter"
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    assert sprint_db.calls[0].get("sprint_id") == 2


def test_weak_close_does_not_hold_the_sprint():
    uc, _, _ = _uc(
        [_done(close_quality="weak"), _done(task_id=2, close_quality="ok")],
        TrajectoryHint("next_sprint", "можно дальше", False),
    )
    result = asyncio.run(uc(7, authorization="Bearer t"))
    assert result.ok is True
    assert result.status == "demo"


def test_appeal_is_spent_on_force_and_cleared_when_the_next_sprint_opens():
    sprint_db = RecordingSprint()
    uc, _, _ = _uc(
        [_done(close_quality="weak")],
        TrajectoryHint("hold_sprint", "hold", True),
        sprint_db=sprint_db,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t", force=True, consume_appeal=True))
    assert draft.status == "demo"
    stored = asyncio.run(uc.career_db.get(7))
    assert stored is not None and stored.appeal_used is True
    letter = _held(uc)
    assert letter.letter is not None and letter.letter.kind == "frozen"
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    stored = asyncio.run(uc.career_db.get(7))
    assert stored is not None and stored.appeal_used is False


def test_force_completes_and_stores_forced_mode():
    sprint_db = RecordingSprint()
    uc, gateway, _ = _uc(
        [_done(close_quality="weak")],
        TrajectoryHint("hold_sprint", "hold", True),
        sprint_db=sprint_db,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t", force=True))
    assert draft.status == "demo"
    letter = _held(uc)
    assert letter.letter is not None and letter.letter.kind == "frozen"
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    assert result.forced is True
    assert result.status == "project finished"
    assert gateway.calls == 2
    assert sprint_db.calls[0]["close_mode"] == "forced"


def test_ok_complete_stores_ok_mode():
    sprint_db = RecordingSprint()
    uc, _, _ = _uc(
        [_done(close_quality="ok")],
        TrajectoryHint("next_sprint", "ok", False),
        sprint_db=sprint_db,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t"))
    assert draft.status == "demo"
    letter = _held(uc)
    assert letter.letter is not None and letter.letter.kind == "promote"
    assert letter.letter.new_grade == "junior"
    assert letter.letter.bonus_paid == 22_000
    assert any("Премия целиком" in fact for fact in letter.letter.facts)
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    assert result.forced is False
    assert sprint_db.calls[0]["close_mode"] == "ok"


def test_evaluate_hold_pure():
    ok = evaluate_sprint_hold([SimpleNamespace(close_quality="ok")], SimpleNamespace(block_next_sprint=False, reason=""))
    assert ok.hold is False
    weak = evaluate_sprint_hold([SimpleNamespace(close_quality="weak")], SimpleNamespace(block_next_sprint=False, reason=""))
    assert weak.hold is False
    assert weak.code == "ok"
    traj = evaluate_sprint_hold([SimpleNamespace(close_quality="ok")], SimpleNamespace(block_next_sprint=True, reason="жди"))
    assert traj.hold is True
    assert traj.code == "trajectory"
    missing = evaluate_sprint_hold([SimpleNamespace(close_quality="ok")], None)
    assert missing.hold is True
    assert missing.code == "trajectory_unavailable"


def test_hold_when_trajectory_unavailable():
    uc, gateway, _ = _uc([_done(close_quality="ok")], None)
    result = asyncio.run(uc(7, authorization="Bearer t"))
    assert result.error == "hold"
    assert gateway.calls == 1
    assert "траектори" in (result.message or "").lower()


def test_force_when_trajectory_unavailable():
    sprint_db = RecordingSprint()
    uc, _, _ = _uc([_done(close_quality="ok")], None, sprint_db=sprint_db)
    asyncio.run(uc(7, authorization="Bearer t", force=True))
    _held(uc)
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    assert result.forced is True
    assert sprint_db.calls[0]["close_mode"] == "forced"


def test_rollback_reopens_sprint_when_next_sprint_create_fails():
    class BoomSprint(RecordingSprint):
        async def create_sprint(self, sprint):
            return False

    class TemplatesWithNext:
        async def get_template_by_id(self, template_id: int):
            return SimpleNamespace(
                sprints=[
                    SimpleNamespace(order=1, tasks=[]),
                    SimpleNamespace(
                        order=2,
                        tasks=[SimpleNamespace(title="n", description="d")],
                    ),
                ]
            )

    class TasksWithCreate(FakeTasks):
        async def create_task(self, task):
            raise AssertionError("should not create tasks if sprint create failed")

    sprint_db = BoomSprint()
    gateway = FakeTrajectory(TrajectoryHint("next_sprint", "ok", False))
    uc = CompleteSprintUseCase(
        task_db=TasksWithCreate([_done(close_quality="ok")]),
        sprint_db=sprint_db,
        user_project_db=FakeProjectDB(),
        project_db=TemplatesWithNext(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=gateway,
        career_db=FakeCareerDB(),
    )
    asyncio.run(uc(7, authorization="Bearer t"))
    _held(uc)
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.error == "update_failed"
    assert any(c.get("new_status") == "completed" and c.get("sprint_id") == 2 for c in sprint_db.calls)
    assert any(
        c.get("old_status") == "completed"
        and c.get("new_status") == "active"
        and c.get("sprint_id") == 2
        for c in sprint_db.calls
    )


def test_rollback_refuses_reopen_if_next_sprint_cancel_fails():
    class StickyNextSprint(RecordingSprint):
        async def create_sprint(self, sprint):
            self.created_id = sprint.sprint_id
            return True

        async def update_sprint(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("new_status") == "cancelled":
                return False
            return True

    class TemplatesWithNext:
        async def get_template_by_id(self, template_id: int):
            return SimpleNamespace(
                sprints=[
                    SimpleNamespace(order=1, tasks=[]),
                    SimpleNamespace(
                        order=2,
                        tasks=[SimpleNamespace(title="n", description="d")],
                    ),
                ]
            )

    class BoomTasks(FakeTasks):
        async def create_task(self, task):
            return False

    sprint_db = StickyNextSprint()
    uc = CompleteSprintUseCase(
        task_db=BoomTasks([_done(close_quality="ok")]),
        sprint_db=sprint_db,
        user_project_db=FakeProjectDB(),
        project_db=TemplatesWithNext(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("next_sprint", "ok", False)),
        career_db=FakeCareerDB(),
    )
    asyncio.run(uc(7, authorization="Bearer t"))
    _held(uc)
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.error == "update_failed"
    assert "не восстановлен" in (result.message or "").lower()
    assert not any(
        c.get("old_status") == "completed" and c.get("new_status") == "active"
        for c in sprint_db.calls
    )


def test_empty_next_sprint_template_blocks_before_close():
    class TemplatesEmptyNext:
        async def get_template_by_id(self, template_id: int):
            return SimpleNamespace(
                sprints=[
                    SimpleNamespace(order=1, tasks=[SimpleNamespace(title="a", description="d")]),
                    SimpleNamespace(order=2, tasks=[]),
                ]
            )

    sprint_db = RecordingSprint()
    uc = CompleteSprintUseCase(
        task_db=FakeTasks([_done(close_quality="ok")]),
        sprint_db=sprint_db,
        user_project_db=FakeProjectDB(),
        project_db=TemplatesEmptyNext(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("next_sprint", "ok", False)),
        career_db=FakeCareerDB(),
    )
    result = asyncio.run(uc(7, authorization="Bearer t"))
    assert result.error == "empty_next_sprint"
    assert sprint_db.calls == []
