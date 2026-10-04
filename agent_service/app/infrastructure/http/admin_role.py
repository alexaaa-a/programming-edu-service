import logging
from typing import Any

import httpx


ADMIN_ROLES = frozenset({"admin", "superadmin"})
KNOWN_ROLES = frozenset({"user", "admin", "superadmin"})


class HttpAdminRoleGateway:
    def __init__(
            self,
            settings: Any,
            client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._client = client
        self._logger = logger

    async def get_my_role(self, authorization: str) -> str:
        base = self._settings.user_gateway_settings.url.rstrip("/")
        url = f"{base}/user/v1/users/admins/me/role"
        headers = {"Accept": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        try:
            response = await self._client.get(url, headers=headers)
        except Exception:
            self._logger.exception("Failed to fetch admin role from user_service")
            return "user"
        if response.status_code != 200:
            self._logger.warning("user_service admin role failed: status=%s", response.status_code)
            return "user"
        try:
            payload = response.json()
        except Exception:
            self._logger.exception("Invalid admin role payload from user_service")
            return "user"
        role = str((payload or {}).get("role") or "user").strip().lower()
        return role if role in KNOWN_ROLES else "user"


def is_admin(role: str) -> bool:
    return role in ADMIN_ROLES
