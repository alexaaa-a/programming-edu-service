import logging
from typing import Any

import httpx

from agent_service.app.application.trajectory import TrajectorySnapshot


class HttpTrajectoryGateway:
    def __init__(
            self,
            settings: Any,
            client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._client = client
        self._logger = logger

    async def get_trajectory(
            self,
            authorization: str,
            task_id: int | None = None,
    ) -> TrajectorySnapshot | None:
        base = self._settings.submission_gateway_settings.url.rstrip("/")
        url = f"{base}/submission/v1/submissions/me/trajectory"
        headers = {"Accept": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        params = {"task_id": task_id} if task_id is not None else None
        try:
            response = await self._client.get(url, headers=headers, params=params)
        except Exception:
            self._logger.exception("Failed to fetch trajectory from submission_service")
            return None
        if response.status_code != 200:
            self._logger.warning(
                "submission_service trajectory failed: status=%s",
                response.status_code,
            )
            return None
        try:
            payload = response.json()
        except Exception:
            self._logger.exception("Invalid trajectory payload from submission_service")
            return None
        if not isinstance(payload, dict):
            return None
        return _snapshot(payload)


def _snapshot(payload: dict) -> TrajectorySnapshot:
    failed = payload.get("failed_criteria")
    criteria: list[str] = []
    if isinstance(failed, list):
        criteria = [str(item).strip() for item in failed if str(item).strip()]
    focus = payload.get("focus") if isinstance(payload.get("focus"), dict) else {}
    nudge = payload.get("nudge") if isinstance(payload.get("nudge"), dict) else {}
    steps_raw = focus.get("steps")
    steps = [str(item).strip() for item in steps_raw if str(item).strip()] if isinstance(steps_raw, list) else []
    recs_raw = payload.get("recommendations")
    recommendations = (
        [
            str(item.get("title") or "").strip()
            for item in recs_raw
            if isinstance(item, dict) and str(item.get("title") or "").strip()
        ]
        if isinstance(recs_raw, list)
        else []
    )
    return TrajectorySnapshot(
        action=str(payload.get("action") or ""),
        reason=str(payload.get("reason") or ""),
        mastery=_as_float(payload.get("mastery")),
        difficulty=_as_float(payload.get("difficulty")),
        pace=_as_float(payload.get("pace")),
        readiness=_as_float(payload.get("readiness")),
        current_score=_as_int(payload.get("current_score")),
        current_attempts=_as_int(payload.get("current_attempts")) or 0,
        failed_criteria=criteria,
        block_next_sprint=bool(payload.get("block_next_sprint")),
        block_close=bool(payload.get("block_close")),
        focus_skill=str(focus.get("skill_id") or ""),
        focus_title=str(focus.get("title") or ""),
        focus_kind=str(focus.get("kind") or ""),
        focus_why=str(focus.get("why") or ""),
        focus_mastery=_as_float(focus.get("mastery")),
        focus_steps=steps,
        focus_mentor=str(focus.get("mentor") or ""),
        recommendations=recommendations,
        nudge_kind=str(nudge.get("kind") or ""),
        nudge_task_id=_as_int(nudge.get("task_id")),
        nudge_hours=_as_int(nudge.get("hours_since")) or 0,
        nudge_score=_as_int(nudge.get("score")),
        nudge_detail=str(nudge.get("detail") or ""),
    )


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class HttpTaskTestsGateway:
    def __init__(
            self,
            settings: Any,
            client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._client = client
        self._logger = logger

    async def get_task_tests(self, task_id: int, user_id: str) -> str | None:
        token = str(getattr(self._settings.submission_gateway_settings, "internal_token", "") or "")
        if not token.strip():
            self._logger.info("task_tests.disabled reason=no_internal_token")
            return None
        base = self._settings.submission_gateway_settings.url.rstrip("/")
        url = f"{base}/submission/v1/internal/tasks/{int(task_id)}/tests"
        try:
            response = await self._client.get(
                url,
                headers={"X-Internal-Token": token, "Accept": "application/json"},
                params={"user_id": str(user_id)},
            )
        except Exception:
            self._logger.exception("Failed to fetch task tests from submission_service")
            return None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            self._logger.warning(
                "submission_service task tests failed: status=%s",
                response.status_code,
            )
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        tests = str(payload.get("tests") or "")
        return tests or None

    async def get_drill_tests(self, drill_id: str) -> tuple[str, str] | None:
        token = self._internal_token()
        if not token:
            return None
        base = self._settings.submission_gateway_settings.url.rstrip("/")
        url = f"{base}/submission/v1/internal/drills/{drill_id}"
        try:
            response = await self._client.get(
                url,
                headers={"X-Internal-Token": token, "Accept": "application/json"},
            )
        except Exception:
            self._logger.exception("Failed to fetch drill tests from submission_service")
            return None
        if response.status_code != 200:
            if response.status_code != 404:
                self._logger.warning("submission_service drill failed: status=%s", response.status_code)
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        tests = str(payload.get("tests") or "")
        if not tests:
            return None
        return tests, str(payload.get("skill_id") or "")

    async def report_drill_result(
            self,
            drill_id: str,
            user_id: str,
            passed: int,
            total: int,
    ) -> bool:
        token = self._internal_token()
        if not token:
            return False
        base = self._settings.submission_gateway_settings.url.rstrip("/")
        url = f"{base}/submission/v1/internal/drills/{drill_id}/result"
        try:
            response = await self._client.post(
                url,
                headers={"X-Internal-Token": token, "Accept": "application/json"},
                json={"user_id": int(user_id), "passed": int(passed), "total": int(total)},
            )
        except Exception:
            self._logger.exception("Failed to report a drill run to submission_service")
            return False
        if response.status_code != 200:
            self._logger.warning("submission_service drill result failed: status=%s", response.status_code)
            return False
        return True

    def _internal_token(self) -> str:
        token = str(getattr(self._settings.submission_gateway_settings, "internal_token", "") or "")
        if not token.strip():
            self._logger.info("drills.disabled reason=no_internal_token")
            return ""
        return token
