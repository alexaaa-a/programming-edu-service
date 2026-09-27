import asyncio
from datetime import datetime
from types import SimpleNamespace

from task_service.app.application.close_gate import ReviewSnapshot
from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.review_gateway import TrajectoryHint
from task_service.app.application.use_case.sprint.complete_sprint import CompleteSprintUseCase
from task_service.app.application.weak_tail import append_weak_tail, failed_criterion_from_latest
from task_service.tests.test_complete_sprint import (
    FakeCareerDB,
    FakeProducer,
    FakeProjectDB,
    FakeTasks,
    FakeTemplates,
    FakeTrajectory,
    RecordingSprint,
)


def test_tail_appends_one_criterion_and_keeps_the_brief():
    brief = "Сложи два числа.\n\ndef add(a, b):\n    pass"
    updated = append_weak_tail(brief, "проверить отрицательные числа")
    assert updated.startswith(brief)
    assert "def add(a, b):" in updated
    assert updated.endswith("Осталось с прошлого ревью: проверить отрицательные числа")
    assert append_weak_tail(updated, "проверить отрицательные числа") == updated
    assert append_weak_tail(brief, "   ") == brief


def test_latest_submission_supplies_the_only_failed_criterion():
    older = ReviewSnapshot(
        status="reviewed",
        score=4,
        created_at="2026-09-01T10:00:00",
        failed_criteria=("старый провал",),
    )
    latest = ReviewSnapshot(
        status="reviewed",
        score=5,
        created_at="2026-09-02T10:00:00",
        failed_criteria=("свежий провал", "второй"),
    )
    assert failed_criterion_from_latest([older, latest]) == "свежий провал"
    clean_latest = ReviewSnapshot(
        status="reviewed",
        score=6,
        created_at="2026-09-03T10:00:00",
        failed_criteria=(),
    )
    assert failed_criterion_from_latest([latest, clean_latest]) is None


def test_weak_close_tails_into_the_first_next_task_without_cutting_salary():
    brief = "Сложи два числа.\n\ndef add(a, b):\n    pass"

    class TemplatesWithNext:
        async def get_template_by_id(self, template_id: int):
            return SimpleNamespace(
                sprints=[
                    SimpleNamespace(order=1, tasks=[]),
                    SimpleNamespace(
                        order=2,
                        tasks=[
                            SimpleNamespace(title="Дальше", description=brief),
                            SimpleNamespace(title="Вторая", description="без хвоста"),
                        ],
                    ),
                ]
            )

    class RecordingTasks(FakeTasks):
        def __init__(self, tasks: list[TaskDTO]) -> None:
            super().__init__(tasks)
            self.created: list[TaskDTO] = []

        async def create_task(self, task: TaskDTO) -> bool:
            self.created.append(task)
            return True

    class SprintThatOpens(RecordingSprint):
        async def create_sprint(self, sprint) -> bool:
            return True

    class Reviews:
        def __init__(self) -> None:
            self.task_ids: list[int] = []

        async def get_task_reviews(self, task_id: int, authorization: str):
            self.task_ids.append(task_id)
            if task_id != 8:
                return [
                    ReviewSnapshot(
                        status="reviewed",
                        score=3,
                        created_at="2026-09-01T10:00:00",
                        failed_criteria=("не этот",),
                    )
                ]
            return [
                ReviewSnapshot(
                    status="reviewed",
                    score=4,
                    created_at="2026-09-01T10:00:00",
                    failed_criteria=("старый провал",),
                ),
                ReviewSnapshot(
                    status="reviewed",
                    score=5,
                    created_at="2026-09-02T10:00:00",
                    failed_criteria=("проверить отрицательные", "ещё один"),
                ),
            ]

    tasks = RecordingTasks(
        [
            _done(task_id=3, close_quality="weak"),
            _done(task_id=8, close_quality="weak"),
            _done(task_id=9, close_quality="ok"),
        ]
    )
    career = FakeCareerDB()
    reviews = Reviews()
    uc = CompleteSprintUseCase(
        task_db=tasks,
        sprint_db=SprintThatOpens(),
        user_project_db=FakeProjectDB(),
        project_db=TemplatesWithNext(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("hold_sprint", "hold", True)),
        career_db=career,
        review_gateway=reviews,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t", force=True))
    assert draft.status == "demo"
    assert draft.demo is not None
    assert "проверить отрицательные" in draft.demo.question
    letter = asyncio.run(
        uc.submit_demo(
            7,
            pitch="Собрали поиск по заказам. Клиент находит позицию за один запрос.",
            answer="Критерий закрыли тестом и повторным ревью.",
        )
    )
    assert letter.letter is not None
    assert letter.letter.new_salary == 70_000
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    assert reviews.task_ids == [8, 8]
    assert tasks.created[0].description.startswith(brief)
    assert "def add(a, b):" in tasks.created[0].description
    assert tasks.created[0].description.endswith(
        "Осталось с прошлого ревью: проверить отрицательные"
    )
    assert tasks.created[1].description == "без хвоста"
    stored = asyncio.run(career.get(7))
    assert stored is not None
    assert stored.salary == 70_000


def test_ok_close_does_not_append_a_tail():
    class TemplatesWithNext:
        async def get_template_by_id(self, template_id: int):
            return SimpleNamespace(
                sprints=[
                    SimpleNamespace(order=1, tasks=[]),
                    SimpleNamespace(
                        order=2,
                        tasks=[SimpleNamespace(title="Дальше", description="чистый бриф")],
                    ),
                ]
            )

    class RecordingTasks(FakeTasks):
        def __init__(self, tasks: list[TaskDTO]) -> None:
            super().__init__(tasks)
            self.created: list[TaskDTO] = []

        async def create_task(self, task: TaskDTO) -> bool:
            self.created.append(task)
            return True

    class SprintThatOpens(RecordingSprint):
        async def create_sprint(self, sprint) -> bool:
            return True

    class Reviews:
        async def get_task_reviews(self, task_id: int, authorization: str):
            raise AssertionError("ok close does not look up a tail")

    tasks = RecordingTasks([_done(close_quality="ok")])
    uc = CompleteSprintUseCase(
        task_db=tasks,
        sprint_db=SprintThatOpens(),
        user_project_db=FakeProjectDB(),
        project_db=TemplatesWithNext(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("next_sprint", "ok", False)),
        career_db=FakeCareerDB(),
        review_gateway=Reviews(),
    )
    asyncio.run(uc(7, authorization="Bearer t"))
    asyncio.run(
        uc.submit_demo(
            7,
            pitch="Собрали поиск по заказам. Клиент находит позицию за один запрос.",
            answer="Критерий закрыли тестом и повторным ревью.",
        )
    )
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True
    assert tasks.created[0].description == "чистый бриф"


def test_weak_peer_review_does_not_steal_the_tail():
    from task_service.app.application.peer_review import PEER_REVIEW_TITLE

    class Reviews:
        def __init__(self) -> None:
            self.task_ids: list[int] = []

        async def get_task_reviews(self, task_id: int, authorization: str):
            self.task_ids.append(task_id)
            text = "заметка мимо" if task_id == 8 else "критерий задачи"
            return [
                ReviewSnapshot(
                    status="reviewed",
                    score=4,
                    created_at="2026-09-02T10:00:00",
                    failed_criteria=(text,),
                )
            ]

    review = _done(task_id=8, close_quality="weak")
    review.title = PEER_REVIEW_TITLE
    reviews = Reviews()
    uc = CompleteSprintUseCase(
        task_db=FakeTasks([_done(task_id=3, close_quality="weak"), review]),
        sprint_db=RecordingSprint(),
        user_project_db=FakeProjectDB(),
        project_db=FakeTemplates(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("next_sprint", "ok", False)),
        career_db=FakeCareerDB(),
        review_gateway=reviews,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t", force=True))
    assert draft.demo is not None
    assert "критерий задачи" in draft.demo.question
    assert reviews.task_ids == [3]


def test_weak_incident_does_not_supply_the_tail():
    from task_service.app.application.night_incident import NIGHT_INCIDENT_TITLE

    class Reviews:
        def __init__(self) -> None:
            self.task_ids: list[int] = []

        async def get_task_reviews(self, task_id: int, authorization: str):
            self.task_ids.append(task_id)
            text = "ночной ноль" if task_id == 8 else "критерий задачи"
            return [
                ReviewSnapshot(
                    status="reviewed",
                    score=4,
                    created_at="2026-09-02T10:00:00",
                    failed_criteria=(text,),
                )
            ]

    incident = _done(task_id=8, close_quality="weak")
    incident.title = NIGHT_INCIDENT_TITLE
    reviews = Reviews()
    uc = CompleteSprintUseCase(
        task_db=FakeTasks([_done(task_id=3, close_quality="weak"), incident]),
        sprint_db=RecordingSprint(),
        user_project_db=FakeProjectDB(),
        project_db=FakeTemplates(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("next_sprint", "ok", False)),
        career_db=FakeCareerDB(),
        review_gateway=reviews,
    )
    draft = asyncio.run(uc(7, authorization="Bearer t", force=True))
    assert draft.demo is not None
    assert "критерий задачи" in draft.demo.question
    assert reviews.task_ids == [3]


def _done(**kwargs) -> TaskDTO:
    return TaskDTO(
        task_id=kwargs.get("task_id", 1),
        user_id=7,
        user_project_id=1,
        sprint_id=2,
        title="t",
        description="d",
        status="done",
        created_at=datetime.now(),
        completed_at=datetime.now(),
        close_quality=kwargs.get("close_quality"),
    )
