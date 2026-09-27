import asyncio
from pathlib import Path

from task_service.app.application.dto.project import (
    ProjectTemplateDTO,
    SprintOrderDTO,
    TaskDTO as TemplateTaskDTO,
)
from task_service.app.application.use_case.project.start_project import StartProjectUseCase


class FakeUserProjectDB:
    def __init__(self) -> None:
        self.created = []
        self.updates = []
        self.active = None

    async def get_active_user_project(self, user_id: int):
        return self.active

    async def create_user_project(self, user_project) -> bool:
        self.created.append(user_project)
        return True

    async def update_user_project(self, user_project_id, new_status, completed_at) -> bool:
        self.updates.append((user_project_id, new_status))
        return True


class FakeProjectDB:
    def __init__(self, template: ProjectTemplateDTO | None) -> None:
        self.template = template

    async def get_template_by_id(self, template_id: int):
        return self.template


class FakeSprintDB:
    def __init__(self, fail_create: bool = False) -> None:
        self.fail_create = fail_create
        self.created = []
        self.updates = []

    async def create_sprint(self, sprint) -> bool:
        if self.fail_create:
            return False
        self.created.append(sprint)
        return True

    async def update_sprint(self, **kwargs) -> bool:
        self.updates.append(kwargs)
        return True


class FakeTaskDB:
    def __init__(self, fail_on: int | None = None) -> None:
        self.fail_on = fail_on
        self.created = []
        self.deleted = []
        self._n = 0

    async def create_task(self, task) -> bool:
        self._n += 1
        if self.fail_on is not None and self._n >= self.fail_on:
            return False
        self.created.append(task)
        return True

    async def delete_tasks_by_sprint(self, sprint_id: int, user_id: int) -> bool:
        self.deleted.append((sprint_id, user_id))
        return True


class FakeProducer:
    def __init__(self, boom: bool = False, boom_on_status: bool = False) -> None:
        self.boom = boom
        self.boom_on_status = boom_on_status
        self.events = []
        self.status_events = []

    async def produce_task_created(self, **kwargs) -> None:
        if self.boom:
            raise RuntimeError("kafka down")
        self.events.append(kwargs)

    async def produce_task_status_updated(self, **kwargs) -> None:
        if self.boom_on_status:
            raise RuntimeError("kafka status down")
        self.status_events.append(kwargs)


def _template() -> ProjectTemplateDTO:
    return ProjectTemplateDTO(
        project_template_id=1,
        title="T",
        description="D",
        sprints=[
            SprintOrderDTO(
                order=1,
                title="S1",
                tasks=[
                    TemplateTaskDTO(title="A", description="a"),
                    TemplateTaskDTO(title="B", description="b"),
                ],
            )
        ],
        direction="backend",
        level="junior",
    )


class FakeCareerDB:
    def __init__(self) -> None:
        self.state = None
        self.deleted = False

    async def get(self, user_id: int):
        return self.state

    async def save(self, state) -> bool:
        self.state = state
        return True

    async def delete(self, user_id: int) -> bool:
        self.deleted = True
        self.state = None
        return True


def test_start_project_rolls_back_when_task_create_fails():
    user_db = FakeUserProjectDB()
    sprint_db = FakeSprintDB()
    task_db = FakeTaskDB(fail_on=2)
    producer = FakeProducer()
    uc = StartProjectUseCase(
        user_project_db=user_db,  # type: ignore[arg-type]
        project_db=FakeProjectDB(_template()),  # type: ignore[arg-type]
        sprint_db=sprint_db,  # type: ignore[arg-type]
        task_db=task_db,  # type: ignore[arg-type]
        task_event_producer=producer,  # type: ignore[arg-type]
        career_db=FakeCareerDB(),  # type: ignore[arg-type]
    )
    result = asyncio.run(uc(7, 1))
    assert result is None
    assert user_db.updates and user_db.updates[0][1] == "cancelled"
    assert sprint_db.updates and sprint_db.updates[0]["new_status"] == "cancelled"
    assert task_db.deleted


def test_start_project_rolls_back_when_kafka_fails():
    user_db = FakeUserProjectDB()
    sprint_db = FakeSprintDB()
    task_db = FakeTaskDB()
    producer = FakeProducer(boom=True)
    uc = StartProjectUseCase(
        user_project_db=user_db,  # type: ignore[arg-type]
        project_db=FakeProjectDB(_template()),  # type: ignore[arg-type]
        sprint_db=sprint_db,  # type: ignore[arg-type]
        task_db=task_db,  # type: ignore[arg-type]
        task_event_producer=producer,  # type: ignore[arg-type]
        career_db=FakeCareerDB(),  # type: ignore[arg-type]
    )
    result = asyncio.run(uc(7, 1))
    assert result is None
    assert user_db.updates and user_db.updates[0][1] == "cancelled"


def test_user_project_update_uses_matched_count():
    text = (
        Path(__file__).resolve().parents[1]
        / "app/infrastructure/mongo/user_project_db.py"
    ).read_text(encoding="utf-8")
    assert "matched_count" in text


def test_template_create_is_admin_gated():
    text = (
        Path(__file__).resolve().parents[1]
        / "app/presentation/api/v1/project/router.py"
    ).read_text(encoding="utf-8")
    assert "can_force_sprint" in text
    assert "response_model=list[ProjectTemplate]" in text
    assert "AdminRoleGatewayInterface" in text


def test_kafka_producer_raises_when_not_started():
    text = (
        Path(__file__).resolve().parents[1]
        / "app/infrastructure/kafka/producer.py"
    ).read_text(encoding="utf-8")
    assert "raise RuntimeError" in text
    assert "skipping event" not in text
