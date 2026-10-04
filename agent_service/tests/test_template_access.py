import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from agent_service.app.infrastructure.http.admin_role import HttpAdminRoleGateway, is_admin
from agent_service.app.presentation.api.v1.templates.router import (
    GenerateSprintRequest,
    generate_sprint,
)


class _Logger:
    def exception(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass

    def info(self, *args, **kwargs) -> None:
        pass


def _settings(enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        token_settings=SimpleNamespace(secret_key="", algorithm="HS256", allow_dev_auth=True),
        template_settings=SimpleNamespace(enabled=enabled, max_repair_rounds=1),
        user_gateway_settings=SimpleNamespace(url="http://user"),
    )


def _request() -> SimpleNamespace:
    return SimpleNamespace(headers={"X-User-Id": "7", "Authorization": "Bearer t"})


class _Roles:
    def __init__(self, role: str) -> None:
        self.role = role
        self.asked = ""

    async def get_my_role(self, authorization: str) -> str:
        self.asked = authorization
        return self.role


class _UseCase:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_sprint(self, spec, order, used_titles):
        self.calls += 1
        raise AssertionError("не должно вызываться в этих тестах")


def _body() -> GenerateSprintRequest:
    return GenerateSprintRequest(topic="Сервис заказов", sprints=1, tasks_per_sprint=2)


def test_roles_are_closed_by_default():
    assert is_admin("admin") and is_admin("superadmin")
    assert not is_admin("user") and not is_admin("")


def test_the_gateway_asks_user_service_with_the_callers_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/user/v1/users/admins/me/role")
        assert request.headers.get("Authorization") == "Bearer t"
        return httpx.Response(200, json={"role": "superadmin"})

    async def run() -> str:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = HttpAdminRoleGateway(_settings(), client, _Logger())
        return await gateway.get_my_role("Bearer t")

    assert asyncio.run(run()) == "superadmin"


def test_an_unreachable_user_service_means_no_rights():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет связи")

    async def run() -> str:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = HttpAdminRoleGateway(_settings(), client, _Logger())
        return await gateway.get_my_role("Bearer t")

    assert asyncio.run(run()) == "user"


def test_a_plain_user_gets_403_and_the_model_is_not_called():
    uc = _UseCase()
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            generate_sprint(
                request=_request(),
                body=_body(),
                uc=uc,
                roles=_Roles("user"),
                settings=_settings(),
            )
        )
    assert error.value.status_code == 403
    assert uc.calls == 0


def test_a_switched_off_generator_answers_503_before_asking_the_role():
    roles = _Roles("admin")
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            generate_sprint(
                request=_request(),
                body=_body(),
                uc=_UseCase(),
                roles=roles,
                settings=_settings(enabled=False),
            )
        )
    assert error.value.status_code == 503
    assert roles.asked == ""


def test_an_anonymous_call_is_401():
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            generate_sprint(
                request=SimpleNamespace(headers={}),
                body=_body(),
                uc=_UseCase(),
                roles=_Roles("admin"),
                settings=_settings(),
            )
        )
    assert error.value.status_code == 401
