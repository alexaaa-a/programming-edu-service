import logging
from datetime import datetime
from typing import Any

import httpx

from task_service.app.application.close_gate import ReviewSnapshot
from task_service.app.application.interfaces.review_gateway import (
    TaskReviewGatewayInterface,
    TrajectoryGatewayInterface,
    TrajectoryHint,
)


class HttpTaskReviewGateway(TaskReviewGatewayInterface, TrajectoryGatewayInterface):
    def __init__(
            self,
            settings: Any,
            client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._client = client
        self._logger = logger

    async def get_task_reviews(
            self,
            task_id: int,
            authorization: str,
    ) -> list[ReviewSnapshot] | None:
        base = self._settings.submission_gateway_settings.url.rstrip("/")
        url = f"{base}/submission/v1/tasks/{task_id}/submissions"
        headers = {"Accept": "application/json"}
        if authorization:
            headers["Authorization"] = authorization
        try:
            response = await self._client.get(url, headers=headers)
        except Exception:
            self._logger.exception("Failed to fetch task reviews from submission_service")
            return None

        if response.status_code == 404:
            return []
        if response.status_code != 200:
            self._logger.warning(
                "submission_service reviews failed: status=%s task_id=%s",
                response.status_code,
                task_id,
            )
            return None

        try:
            payload = response.json()
        except Exception:
            self._logger.exception("Invalid reviews payload from submission_service")
            return None

        if not isinstance(payload, list):
            return None
        return [_snapshot(item) for item in payload if isinstance(item, dict)]

    async def get_trajectory(
            self,
            authorization: str,
            task_id: int | None = None,
    ) -> TrajectoryHint | None:
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
        return TrajectoryHint(
            action=str(payload.get("action") or ""),
            reason=str(payload.get("reason") or ""),
            block_next_sprint=bool(payload.get("block_next_sprint")),
            mastery=float(payload.get("mastery") or 0),
            difficulty=float(payload.get("difficulty") or 0),
            pace=float(payload.get("pace") or 0),
            readiness=float(payload.get("readiness") or 0),
        )


def _snapshot(item: dict) -> ReviewSnapshot:
    review = item.get("review")
    score = None
    if isinstance(review, dict) and review.get("score") is not None:
        try:
            score = float(review["score"])
        except (TypeError, ValueError):
            score = None
    created_at = _parse_stamp(item.get("created_at"))
    reviewed_at = _parse_stamp(item.get("reviewed_at"))
    return ReviewSnapshot(
        status=str(item.get("status") or ""),
        score=score,
        created_at=created_at,
        reviewed_at=reviewed_at,
        failed_criteria=_failed_criteria(review),
    )


def _failed_criteria(review: object) -> tuple[str, ...]:
    if not isinstance(review, dict):
        return ()
    raw = review.get("criteria")
    if not isinstance(raw, list):
        return ()
    failed: list[str] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("passed") is True:
            continue
        text = " ".join(str(item.get("text") or "").split()).strip()
        if text:
            failed.append(text)
    return tuple(failed)


def _parse_stamp(raw: object) -> datetime | str | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
    return None
