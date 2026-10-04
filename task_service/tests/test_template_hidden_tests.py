import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from task_service.app.application.dto.project import (
    ProjectTemplateDTO,
    SprintOrderDTO,
    TaskDTO,
)
from task_service.app.presentation.api.v1.project.router import (
    create_project_template,
    get_project_templates,
)
from task_service.app.presentation.api.v1.project.schema import (
    ProjectTemplate,
    SprintOrder,
    Task,
)


TESTS = "from solution import f\n\n\ndef test_f():\n    assert f() == 1\n"


class _Token:
    @staticmethod
    def decode_token(token: str) -> int | None:
        return 7 if token == "ok" else None


class _Roles:
    def __init__(self, role: str = "admin") -> None:
        self.role = role

    async def get_my_role(self, authorization: str) -> str:
        return self.role


class _Create:
    def __init__(self) -> None:
        self.dto: ProjectTemplateDTO | None = None

    async def __call__(self, dto: ProjectTemplateDTO) -> bool:
        self.dto = dto
        return True


def _request() -> SimpleNamespace:
    return SimpleNamespace(headers={"Authorization": "Bearer ok"})


def _body() -> ProjectTemplate:
    return ProjectTemplate(
        project_template_id=None,
        title="Сервис заказов",
        description="Мини-бэкенд магазина",
        direction="backend",
        level="junior",
        sprints=[
            SprintOrder(
                order=1,
                title="Спринт 1",
                tasks=[Task(title="Сумма заказа", description="Бриф", tests=TESTS)],
            )
        ],
    )


def test_created_template_keeps_the_hidden_tests():
    uc = _Create()
    asyncio.run(
        create_project_template(
            request=_request(),
            token_service=_Token(),
            admin_roles=_Roles("admin"),
            uc=uc,
            body=_body(),
        )
    )
    assert uc.dto is not None
    assert uc.dto.sprints[0].tasks[0].tests == TESTS


def test_a_plain_user_cannot_create_a_template():
    uc = _Create()
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_project_template(
                request=_request(),
                token_service=_Token(),
                admin_roles=_Roles("user"),
                uc=uc,
                body=_body(),
            )
        )
    assert error.value.status_code == 403
    assert uc.dto is None


def test_the_template_list_does_not_hand_tests_to_the_student():
    template = ProjectTemplateDTO(
        project_template_id=1,
        title="Сервис заказов",
        description="Мини-бэкенд магазина",
        direction="backend",
        level="junior",
        sprints=[
            SprintOrderDTO(
                order=1,
                title="Спринт 1",
                tasks=[TaskDTO(title="Сумма заказа", description="Бриф", tests=TESTS)],
            )
        ],
    )

    async def uc(user_id: int) -> list[ProjectTemplateDTO]:
        return [template]

    result = asyncio.run(
        get_project_templates(request=_request(), token_service=_Token(), uc=uc)
    )
    assert result[0].sprints[0].tasks[0].tests == ""
