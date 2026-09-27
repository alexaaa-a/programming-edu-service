import asyncio
from datetime import datetime
from types import SimpleNamespace

from task_service.app.application.career import CareerState
from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.review_gateway import TrajectoryHint
from task_service.app.application.interfaces.career_llm import PeerGrade, PeerSnippet
from task_service.app.application.peer_review import (
    PEER_REVIEW_DESCRIPTION,
    PEER_REVIEW_TITLE,
    found_the_bug,
    peer_review_task_for,
)
from task_service.app.application.use_case.project.start_project import StartProjectUseCase
from task_service.app.application.use_case.sprint.complete_sprint import CompleteSprintUseCase
from task_service.app.application.use_case.tasks.submit_peer_review import SubmitPeerReviewUseCase
from task_service.tests.test_complete_sprint import (
    FakeCareerDB,
    FakeProducer,
    FakeProjectDB,
    FakeTrajectory,
    RecordingSprint,
    _done,
    _held,
)
from task_service.tests.test_start_project_rollback import (
    FakeCareerDB as StartCareerDB,
    FakeProducer as StartProducer,
    FakeProjectDB as StartProjects,
    FakeSprintDB,
    FakeTaskDB,
    FakeUserProjectDB,
    _template,
)


def test_emma_accepts_only_the_sort_bug():
    assert found_the_bug("sorted идёт по возрастанию, а нужны наибольшие")
    assert found_the_bug("берёт меньшие значения вместо больших")
    assert found_the_bug("нет reverse=True, топ должен быть сверху")
    assert not found_the_bug("нет проверки на пустой список")
    assert not found_the_bug("sorted")
    assert not found_the_bug("сортировка по возрастанию")
    assert not found_the_bug("надо проверить числа меньше нуля")
    assert not found_the_bug("максимальная длина строки")
    assert not found_the_bug("надо сделать reverse")
    assert not found_the_bug("по возрастанию больше не работает")
    assert peer_review_task_for("junior") is None
    assert peer_review_task_for("junior_plus")[0] == PEER_REVIEW_TITLE
    assert "убыван" not in PEER_REVIEW_DESCRIPTION
    assert "sorted(scores)" in PEER_REVIEW_DESCRIPTION


class _Tasks:
    def __init__(self, tasks: list[TaskDTO]) -> None:
        self.tasks = list(tasks)
        self.created: list[TaskDTO] = []

    async def get_tasks(self, sprint_id: int, user_id: int):
        return self.tasks

    async def create_task(self, task: TaskDTO) -> bool:
        self.created.append(task)
        return True

    async def delete_tasks_by_sprint(self, sprint_id: int, user_id: int) -> bool:
        return True


class _Opens(RecordingSprint):
    async def create_sprint(self, sprint) -> bool:
        return True


class _Llm:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def generate_peer_snippet(self):
        return PeerSnippet(
            code="def page(items, n):\n    return items[n:]",
            bug="срез начинается с n, первая страница теряется",
        )

    async def grade_peer_note(self, code, bug, note):
        if self.fail:
            return None
        found = "страниц" in note or "страница" in note
        emma = (
            "Эмма: да, первая страница пропала."
            if found
            else "Эмма: дыра в срезе, первая страница не отдаётся."
        )
        return PeerGrade(found=found, emma=emma)

    async def grade_demo_answer(self, criterion, answer):
        return False


def _open(grade: str, career_llm=None):
    tasks = _Tasks([_done(close_quality="ok")])
    career = FakeCareerDB()
    career.state = CareerState(
        user_id=7,
        grade=grade,
        salary=110_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
    )
    project = SimpleNamespace(
        sprints=[
            SimpleNamespace(order=1, tasks=[]),
            SimpleNamespace(
                order=2,
                tasks=[SimpleNamespace(title="Дальше", description="бриф")],
            ),
        ]
    )

    class Templates:
        async def get_template_by_id(self, template_id: int):
            return project

    uc = CompleteSprintUseCase(
        task_db=tasks,
        sprint_db=_Opens(),
        user_project_db=FakeProjectDB(),
        project_db=Templates(),
        task_event_producer=FakeProducer(),
        trajectory_gateway=FakeTrajectory(TrajectoryHint("next_sprint", "ok", False)),
        career_db=career,
        career_llm=career_llm,
    )
    asyncio.run(uc(7, authorization="Bearer t"))
    _held(uc)
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    return result, tasks


def test_peer_review_lands_on_the_sprint_you_enter_as_junior_plus():
    junior, tasks = _open("intern")
    assert junior.ok is True
    assert [task.title for task in tasks.created] == ["Дальше"]

    plus, review_tasks = _open("junior")
    assert plus.ok is True
    assert [task.title for task in review_tasks.created] == ["Дальше", PEER_REVIEW_TITLE]
    assert review_tasks.created[0].description == "бриф"
    assert "sorted(scores)" in review_tasks.created[1].description
    assert review_tasks.created[1].review_bug
    assert review_tasks.created[1].review_bug not in review_tasks.created[1].description


class _MemoryTasks:
    def __init__(self, task: TaskDTO) -> None:
        self.task = task
        self.updates: list[dict] = []

    async def get_task_by_id(self, task_id: int, user_id: int):
        if self.task.task_id != task_id or self.task.user_id != user_id:
            return None
        return self.task

    async def update_task(
            self,
            task_id,
            new_status,
            completed_at=None,
            close_quality=None,
            user_id=None,
            close_note=None,
    ):
        self.updates.append({"status": new_status, "close_quality": close_quality, "close_note": close_note})
        self.task.status = new_status
        self.task.completed_at = completed_at
        self.task.close_quality = close_quality
        self.task.close_note = close_note or None
        return True


class _Producer:
    def __init__(self, boom: bool = False) -> None:
        self.boom = boom
        self.events: list[str] = []

    async def produce_task_status_updated(self, **kwargs):
        if self.boom:
            raise RuntimeError("kafka")
        self.events.append(kwargs["status"])


def _peer_task(**kwargs) -> TaskDTO:
    return TaskDTO(
        task_id=4,
        user_id=7,
        user_project_id=1,
        sprint_id=2,
        title=kwargs.get("title", PEER_REVIEW_TITLE),
        description=PEER_REVIEW_DESCRIPTION,
        status=kwargs.get("status", "todo"),
        created_at=datetime.now(),
        completed_at=None,
    )


def test_emma_closes_the_task_without_a_code_submission():
    tasks = _MemoryTasks(_peer_task())
    producer = _Producer()
    uc = SubmitPeerReviewUseCase(tasks, producer)
    found = asyncio.run(uc(7, 4, "Сортировка по возрастанию, а нужны наибольшие."))
    assert found.ok is True
    assert found.close_quality == "ok"
    assert "меньшие" in (found.emma or "")
    assert producer.events == ["done"]
    again = asyncio.run(uc(7, 4, "ещё раз"))
    assert again.error == "already_done"


def test_a_miss_is_a_weak_close_and_a_normal_task_is_refused():
    tasks = _MemoryTasks(_peer_task())
    missed = asyncio.run(SubmitPeerReviewUseCase(tasks, _Producer())(7, 4, "нет проверки пустого списка"))
    assert missed.close_quality == "weak"
    assert "возрастанию" in (missed.emma or "")

    plain = _MemoryTasks(_peer_task(title="API"))
    refused = asyncio.run(SubmitPeerReviewUseCase(plain, _Producer())(7, 4, "нужен reverse"))
    assert refused.error == "not_peer"
    assert plain.updates == []


def test_produce_failure_reopens_the_peer_review():
    tasks = _MemoryTasks(_peer_task())
    result = asyncio.run(SubmitPeerReviewUseCase(tasks, _Producer(boom=True))(7, 4, "нужен reverse"))
    assert result.error == "produce_failed"
    assert tasks.task.status == "todo"
    assert tasks.task.close_quality is None


def test_second_project_at_junior_plus_includes_the_review():
    career = StartCareerDB()
    career.state = CareerState(
        user_id=7,
        grade="junior_plus",
        salary=150_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
    )
    task_db = FakeTaskDB()
    uc = StartProjectUseCase(
        user_project_db=FakeUserProjectDB(),
        project_db=StartProjects(_template()),
        sprint_db=FakeSprintDB(),
        task_db=task_db,
        task_event_producer=StartProducer(),
        career_db=career,
    )
    assert asyncio.run(uc(7, 1)) is True
    assert [task.title for task in task_db.created] == ["A", "B", PEER_REVIEW_TITLE]


def test_model_hides_the_bug_and_judges_the_note():
    _, tasks = _open("junior", career_llm=_Llm())
    review = tasks.created[1]
    assert "def page" in review.description
    assert "первая страница" not in review.description
    assert review.review_bug == "срез начинается с n, первая страница теряется"

    stored = _peer_task()
    stored.description = review.description
    stored.review_bug = review.review_bug
    missed = asyncio.run(
        SubmitPeerReviewUseCase(_MemoryTasks(stored), _Producer(), career_llm=_Llm())(
            7, 4, "нужен reverse, сортировка не та",
        )
    )
    assert missed.close_quality == "weak"
    assert "страниц" in (missed.emma or "")
    hit = _peer_task()
    hit.description = review.description
    hit.review_bug = review.review_bug
    found = asyncio.run(
        SubmitPeerReviewUseCase(_MemoryTasks(hit), _Producer(), career_llm=_Llm())(
            7, 4, "пропала первая страница",
        )
    )
    assert found.close_quality == "ok"
    assert "страниц" in (found.emma or "")


def test_model_failure_leaves_the_review_open():
    task = _peer_task()
    task.review_bug = "срез начинается с n, первая страница теряется"
    tasks = _MemoryTasks(task)
    result = asyncio.run(
        SubmitPeerReviewUseCase(tasks, _Producer(), career_llm=_Llm(fail=True))(
            7, 4, "пропала первая страница",
        )
    )
    assert result.error == "unread"
    assert tasks.task.status == "todo"
    assert tasks.updates == []
