import random
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from locust import HttpUser, between, task


@dataclass
class UserSession:
    email: str
    password: str
    access_token: str
    refresh_token: str


class GatewayUserFlow(HttpUser):
    wait_time = between(0.2, 1.5)
    host = "http://api.edu.local"

    def on_start(self) -> None:
        self.session = self._register_or_login()

    def _register_or_login(self) -> UserSession:
        suffix = uuid4().hex[:10]
        email = f"locust_{suffix}@example.com"
        password = "LocustPassw0rd!"
        username = f"locust_{suffix}"
        payload = {
            "username": username,
            "password": password,
            "name": "Locust",
            "surname": "User",
            "email": email,
        }

        with self.client.post(
            "/api/user/v1/auth/register",
            json=payload,
            name="auth_register",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                data = resp.json()
                return UserSession(
                    email=email,
                    password=password,
                    access_token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", ""),
                )

            resp.failure(f"register failed: {resp.status_code} {resp.text[:200]}")
            return UserSession(email=email, password=password, access_token="", refresh_token="")

    def _auth_headers(self) -> dict[str, str]:
        token = self.session.access_token if self.session else ""
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    @task(5)
    def get_me(self) -> None:
        self.client.get(
            "/api/user/v1/users/me",
            headers=self._auth_headers(),
            name="users_me",
        )

    @task(3)
    def patch_profile(self) -> None:
        mark = int(time.time()) % 100000
        body: dict[str, Any] = {
            "name": "Locust",
            "surname": "User",
            "username": f"locust_u_{mark}_{random.randint(10, 99)}",
            "email": self.session.email if self.session else "",
            "direction": random.choice(["backend", "frontend", "fullstack"]),
            "level": random.choice(["junior", "middle", "senior"]),
        }
        self.client.patch(
            "/api/user/v1/users/me",
            headers=self._auth_headers(),
            json=body,
            name="users_patch_me",
        )

    @task(1)
    def login_again(self) -> None:
        if not self.session:
            return
        payload = {"email": self.session.email, "password": self.session.password}
        with self.client.post(
            "/api/user/v1/auth/login",
            json=payload,
            name="auth_login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token")
                if token:
                    self.session.access_token = token
                refresh = data.get("refresh_token")
                if refresh:
                    self.session.refresh_token = refresh
                resp.success()
            else:
                resp.failure(f"login failed: {resp.status_code}")
