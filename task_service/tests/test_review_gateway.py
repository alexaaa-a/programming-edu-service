import asyncio
from types import SimpleNamespace

import pytest

httpx = pytest.importorskip("httpx")

from task_service.app.infrastructure.http.submission_reviews import HttpTaskReviewGateway


def _settings(url: str = "http://submission") -> SimpleNamespace:
    return SimpleNamespace(submission_gateway_settings=SimpleNamespace(url=url))


def test_parses_reviews_and_404_as_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/submission/v1/tasks/11/submissions"
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(
            200,
            json=[
                {
                    "status": "reviewed",
                    "created_at": "2026-09-17T12:00:00Z",
                    "review": {
                        "score": 7,
                        "criteria": [
                            {"id": "c1", "text": "вернуть сумму", "passed": True},
                            {"id": "c2", "text": "проверить пустой ввод", "passed": False},
                        ],
                    },
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HttpTaskReviewGateway(_settings(), client, SimpleNamespace(exception=lambda *a, **k: None, warning=lambda *a, **k: None))

    snapshots = asyncio.run(gateway.get_task_reviews(11, "Bearer tok"))
    assert snapshots is not None
    assert len(snapshots) == 1
    assert snapshots[0].score == 7.0
    assert snapshots[0].status == "reviewed"
    assert snapshots[0].failed_criteria == ("проверить пустой ввод",)


def test_404_is_empty_not_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Не найдено"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HttpTaskReviewGateway(
        _settings(),
        client,
        SimpleNamespace(exception=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    snapshots = asyncio.run(gateway.get_task_reviews(11, "Bearer tok"))
    assert snapshots == []


def test_parses_trajectory():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "trajectory" in str(request.url)
        return httpx.Response(
            200,
            json={
                "action": "hold_sprint",
                "reason": "Тяжело",
                "block_next_sprint": True,
                "mastery": 0.4,
                "difficulty": 0.6,
                "pace": 0.2,
                "readiness": 0.5,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HttpTaskReviewGateway(
        _settings(),
        client,
        SimpleNamespace(exception=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    hint = asyncio.run(gateway.get_trajectory("Bearer tok"))
    assert hint is not None
    assert hint.block_next_sprint is True
    assert hint.action == "hold_sprint"
