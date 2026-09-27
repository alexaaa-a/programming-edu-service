import logging
from typing import Any

import httpx

from task_service.app.application.interfaces.career_llm import (
    NightIncidentDraft,
    PeerGrade,
    PeerSnippet,
)


class HttpCareerLlm:
    def __init__(
            self,
            settings: Any,
            client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._client = client
        self._logger = logger

    async def generate_peer_snippet(self) -> PeerSnippet | None:
        payload = await self._post("/agents/v1/career/peer-snippet", None)
        if not isinstance(payload, dict):
            return None
        code = str(payload.get("code") or "").strip()
        bug = " ".join(str(payload.get("bug") or "").split())
        if not code or not bug or bug.lower() in code.lower():
            return None
        return PeerSnippet(code=code, bug=bug)

    async def generate_night_incident(self) -> NightIncidentDraft | None:
        payload = await self._post("/agents/v1/career/night-incident", None)
        if not isinstance(payload, dict):
            return None
        scene = " ".join(str(payload.get("scene") or "").split())
        code = str(payload.get("code") or "").strip()
        expect = " ".join(str(payload.get("expect") or "").split())
        if not scene or not code or not expect or "def " not in code:
            return None
        if expect.lower() in code.lower() or "discounted" in code.lower():
            return None
        return NightIncidentDraft(scene=scene, code=code, expect=expect)

    async def grade_peer_note(self, code: str, bug: str, note: str) -> PeerGrade | None:
        payload = await self._post(
            "/agents/v1/career/peer-grade",
            {"code": code, "bug": bug, "note": note},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("found"), bool):
            return None
        emma = " ".join(str(payload.get("emma") or "").split())
        if not emma:
            return None
        return PeerGrade(found=payload["found"], emma=emma)

    async def grade_demo_answer(self, criterion: str, answer: str) -> bool | None:
        payload = await self._post(
            "/agents/v1/career/demo-grade",
            {"criterion": criterion, "answer": answer},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("addresses"), bool):
            return None
        return payload["addresses"]

    async def _post(self, path: str, body: dict | None) -> dict | None:
        gateway = self._settings.agent_gateway_settings
        token = gateway.token.strip()
        if not token:
            return None
        url = f"{gateway.url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "X-Career-Token": token,
        }
        try:
            response = await self._client.post(
                url,
                json=body,
                headers=headers,
                timeout=gateway.timeout_sec,
            )
        except Exception:
            self._logger.exception("career llm call failed path=%s", path)
            return None
        if response.status_code != 200:
            self._logger.warning(
                "career llm status=%s path=%s",
                response.status_code,
                path,
            )
            return None
        try:
            payload = response.json()
        except Exception:
            self._logger.exception("career llm payload invalid path=%s", path)
            return None
        return payload if isinstance(payload, dict) else None
