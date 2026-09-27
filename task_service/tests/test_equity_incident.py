import asyncio
from datetime import datetime, timezone

from task_service.app.application.career import (
    EQUITY_GRANT,
    INCIDENT_BONUS,
    CareerLetter,
    CareerState,
    accept_letter,
    draft_sprint_letter,
    new_intern,
)
from task_service.app.application.dto.task import TaskDTO
from task_service.app.application.interfaces.review_gateway import TrajectoryHint
from task_service.app.application.night_incident import (
    NIGHT_INCIDENT_TITLE,
    open_night_incident,
)
from task_service.tests.test_complete_sprint import RecordingSprint, _done, _held, _uc


def _strong(**kwargs) -> CareerState:
    base = new_intern(7)
    return CareerState(
        user_id=7,
        grade="strong",
        salary=190_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        letters=kwargs.get("letters", ()),
        created_at=base.created_at,
    )


def _frozen_letter() -> CareerLetter:
    return CareerLetter(
        at=datetime.now(tz=timezone.utc),
        old_salary=110_000,
        new_salary=110_000,
        bonus_paid=0,
        facts=("Зачёт: 0. Слабо: 1.",),
        text="рано",
        kind="frozen",
        old_grade="junior",
        new_grade="junior",
    )


def test_clean_path_to_offer_grants_equity():
    state = _strong()
    letter = draft_sprint_letter(state, [("API", "ok")], trajectory_blocked=False)
    assert letter.new_grade == "offer"
    assert letter.new_salary == 240_000
    assert any("Cliff пройден" in fact for fact in letter.facts)
    pending = CareerState(
        user_id=7,
        grade="strong",
        salary=190_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        pending_letter=letter,
        created_at=state.created_at,
    )
    accepted = accept_letter(pending)
    assert accepted is not None
    assert accepted.equity == EQUITY_GRANT
    assert accepted.salary == 240_000
    assert accepted.grade == "offer"


def test_a_frozen_sprint_blocks_the_cliff():
    state = _strong(letters=(_frozen_letter(),))
    letter = draft_sprint_letter(state, [("API", "ok")], trajectory_blocked=False)
    assert letter.new_grade == "offer"
    assert letter.new_salary == 240_000
    assert any("cliff не пройден" in fact for fact in letter.facts)
    pending = CareerState(
        user_id=7,
        grade="strong",
        salary=190_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        letters=state.letters,
        pending_letter=letter,
        created_at=state.created_at,
    )
    accepted = accept_letter(pending)
    assert accepted is not None
    assert accepted.equity == 0
    assert accepted.salary == 240_000


def test_finished_incident_adds_bonus_and_a_skip_does_not_touch_salary():
    state = new_intern(7)
    done = draft_sprint_letter(
        state,
        [("API", "ok")],
        trajectory_blocked=False,
        incident="done",
    )
    assert done.new_salary == 110_000
    assert done.bonus_paid == 22_000 + INCIDENT_BONUS
    assert any("Разовая премия" in fact for fact in done.facts)
    assert str(INCIDENT_BONUS) in done.text
    quiet = draft_sprint_letter(
        state,
        [("A", "weak"), ("B", "weak")],
        trajectory_blocked=False,
        incident="done",
    )
    assert quiet.kind == "no_raise"
    assert quiet.bonus_paid == INCIDENT_BONUS
    assert "премии в этом спринте нет" not in quiet.text
    assert str(INCIDENT_BONUS) in quiet.text
    skipped = draft_sprint_letter(
        state,
        [("API", "ok")],
        trajectory_blocked=False,
        incident="skipped",
    )
    assert skipped.new_salary == 110_000
    assert skipped.bonus_paid == 22_000
    assert any("500" in fact for fact in skipped.facts)


def _incident(**kwargs) -> TaskDTO:
    task = _done(task_id=kwargs.get("task_id", 2), status=kwargs.get("status", "todo"), close_quality=kwargs.get("close_quality"))
    task.title = NIGHT_INCIDENT_TITLE
    return task


def test_skipped_incident_lets_the_sprint_close():
    uc, _, _ = _uc(
        [_done(close_quality="ok"), _incident()],
        TrajectoryHint("next_sprint", "ok", False),
    )
    opened = asyncio.run(uc(7, authorization="Bearer t"))
    assert opened.status == "demo"
    letter = _held(uc)
    assert letter.letter is not None
    assert letter.letter.new_salary == 110_000
    assert letter.letter.bonus_paid == 22_000
    assert any("500" in fact for fact in letter.letter.facts)


def test_weak_incident_does_not_mark_the_sprint_forced():
    sprint_db = RecordingSprint()
    uc, gateway, _ = _uc(
        [_done(task_id=3, close_quality="ok"), _incident(task_id=9, status="done", close_quality="weak")],
        TrajectoryHint("next_sprint", "ok", False),
        sprint_db=sprint_db,
    )
    opened = asyncio.run(uc(7, authorization="Bearer t"))
    assert opened.status == "demo"
    letter = _held(uc)
    assert letter.letter is not None and letter.letter.kind == "promote"
    result = asyncio.run(uc.accept(7, authorization="Bearer t"))
    assert result.ok is True and result.forced is False
    assert sprint_db.calls[0]["close_mode"] == "ok"
    assert gateway.task_ids == [3, 3]


def test_started_incident_keeps_the_sprint_open():
    uc, _, _ = _uc(
        [_done(close_quality="ok"), _incident(status="review")],
        TrajectoryHint("next_sprint", "ok", False),
    )
    opened = asyncio.run(uc(7, authorization="Bearer t"))
    assert opened.error == "tasks_open"
    assert "инцидент" in (opened.message or "")


def test_weak_incident_does_not_hold_the_sprint():
    uc, _, _ = _uc(
        [_done(close_quality="ok"), _incident(status="done", close_quality="weak")],
        TrajectoryHint("next_sprint", "ok", False),
    )
    opened = asyncio.run(uc(7, authorization="Bearer t"))
    assert opened.status == "demo"
    letter = _held(uc)
    assert letter.letter is not None
    assert letter.letter.bonus_paid == 22_000
    assert letter.letter.new_grade == "junior"
    assert any("слабо" in fact for fact in letter.letter.facts)


class _Career:
    def __init__(self, state) -> None:
        self.state = state

    async def get(self, user_id: int):
        return self.state

    async def save(self, state) -> bool:
        self.state = state
        return True


class _Tasks:
    def __init__(self, current: TaskDTO) -> None:
        self.current = current
        self.created: list[TaskDTO] = []

    async def get_tasks(self, sprint_id: int, user_id: int):
        return [self.current, *self.created]

    async def create_task(self, task: TaskDTO) -> bool:
        self.created.append(task)
        return True

    async def update_task(self, task_id, new_status, completed_at=None, close_quality=None, user_id=None):
        for task in self.created:
            if task.task_id == task_id:
                task.status = new_status
        return True


class _Producer:
    def __init__(self, boom: bool = False) -> None:
        self.boom = boom
        self.created = 0

    async def produce_task_created(self, **kwargs):
        if self.boom:
            raise RuntimeError("kafka")
        self.created += 1


def test_incident_uses_a_generated_snippet_when_the_model_answers():
    career = _Career(new_intern(7))
    tasks = _Tasks(_done(close_quality="ok"))

    class _Llm:
        async def generate_night_incident(self):
            from task_service.app.application.interfaces.career_llm import NightIncidentDraft
            return NightIncidentDraft(
                scene="кэш отдаёт вчерашнюю цену",
                code="def cached_price(store, key):\n    return store[key]",
                expect="Если ключа нет, верни None, а не падай.",
            )

    asyncio.run(open_night_incident(
        task_db=tasks,
        career_db=career,
        producer=_Producer(),
        user_id=7,
        closed=tasks.current,
        quality="ok",
        career_llm=_Llm(),
    ))
    text = tasks.created[0].description
    assert "cached_price" in text
    assert "discounted" not in text
    assert "На доске" in text


def test_incident_opens_once_after_the_first_ok():
    career = _Career(new_intern(7))
    tasks = _Tasks(_done(close_quality="ok"))
    producer = _Producer()
    asyncio.run(open_night_incident(
        task_db=tasks,
        career_db=career,
        producer=producer,
        user_id=7,
        closed=tasks.current,
        quality="weak",
    ))
    assert tasks.created == []
    asyncio.run(open_night_incident(
        task_db=tasks,
        career_db=career,
        producer=producer,
        user_id=7,
        closed=tasks.current,
        quality="ok",
    ))
    assert [task.title for task in tasks.created] == [NIGHT_INCIDENT_TITLE]
    assert career.state.incident_used is True
    assert "15" in tasks.created[0].description or str(INCIDENT_BONUS) in tasks.created[0].description
    asyncio.run(open_night_incident(
        task_db=tasks,
        career_db=career,
        producer=producer,
        user_id=7,
        closed=tasks.current,
        quality="ok",
    ))
    assert len(tasks.created) == 1


def test_a_new_project_can_have_its_own_incident():
    from task_service.app.application.use_case.project.start_project import StartProjectUseCase
    from task_service.tests.test_start_project_rollback import (
        FakeProducer,
        FakeProjectDB,
        FakeSprintDB,
        FakeTaskDB,
        FakeUserProjectDB,
        _template,
    )

    career = _Career(new_intern(7))
    career.state = CareerState(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=True,
        appeal_used=False,
        created_at=career.state.created_at,
    )
    uc = StartProjectUseCase(
        user_project_db=FakeUserProjectDB(),
        project_db=FakeProjectDB(_template()),
        sprint_db=FakeSprintDB(),
        task_db=FakeTaskDB(),
        task_event_producer=FakeProducer(),
        career_db=career,
    )
    assert asyncio.run(uc(7, 1)) is True
    assert career.state.incident_used is False


def test_publish_failure_does_not_spend_the_incident():
    career = _Career(new_intern(7))
    tasks = _Tasks(_done(close_quality="ok"))
    asyncio.run(open_night_incident(
        task_db=tasks,
        career_db=career,
        producer=_Producer(boom=True),
        user_id=7,
        closed=tasks.current,
        quality="ok",
    ))
    assert career.state.incident_used is False
    assert tasks.created[0].status == "cancelled"
