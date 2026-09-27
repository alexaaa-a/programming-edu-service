import asyncio
from types import SimpleNamespace

import httpx
import pytest

from task_service.app.infrastructure.http.admin_role import HttpAdminRoleGateway, can_force_sprint


def test_can_force_sprint_roles():
    assert can_force_sprint("admin") is True
    assert can_force_sprint("superadmin") is True
    assert can_force_sprint("user") is False
    assert can_force_sprint("") is False


def test_admin_role_gateway_parses_role():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/user/v1/users/admins/me/role")
        assert request.headers.get("Authorization") == "Bearer t"
        return httpx.Response(200, json={"role": "admin"})

    async def _run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = HttpAdminRoleGateway(
            SimpleNamespace(user_gateway_settings=SimpleNamespace(url="http://user")),
            client,
            SimpleNamespace(exception=lambda *a, **k: None, warning=lambda *a, **k: None),
        )
        assert await gateway.get_my_role("Bearer t") == "admin"

    asyncio.run(_run())


def test_admin_role_gateway_fail_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    async def _run() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        gateway = HttpAdminRoleGateway(
            SimpleNamespace(user_gateway_settings=SimpleNamespace(url="http://user")),
            client,
            SimpleNamespace(exception=lambda *a, **k: None, warning=lambda *a, **k: None),
        )
        assert await gateway.get_my_role("Bearer t") == "user"

    asyncio.run(_run())
