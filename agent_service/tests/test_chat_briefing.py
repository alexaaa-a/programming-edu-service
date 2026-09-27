import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from agent_service.app.application.dto.chat import ChatTurnResult
from agent_service.app.application.skills.standard_skills import BuildChatPromptsSkill
from agent_service.app.application.team import SARA
from agent_service.app.application.team_router import (
    emma_session_route,
    limit_to_one_speaker,
    route_without_llm,
)
from agent_service.app.application.trajectory import (
    TrajectorySnapshot,
    format_trajectory_briefing,
)
from agent_service.app.application.use_cases.chat_with_team import ChatWithTeamUseCase
from agent_service.app.infrastructure.http.submission_trajectory import HttpTrajectoryGateway


def test_format_includes_action_score_and_failed_criteria():
    text = format_trajectory_briefing(
        TrajectorySnapshot(
            action="chat",
            reason="Балл 4, разбери замечания с командой.",
            mastery=0.4,
            difficulty=0.6,
            pace=0.5,
            readiness=0.45,
            current_score=4,
            current_attempts=1,
            failed_criteria=["Нет проверки пустого ввода", "Нет тестов"],
        )
    )
    assert "разобрать замечания" in text
    assert "4/10" in text
    assert "попыток: 1" in text
    assert "Нет проверки пустого ввода" in text
    assert "M 40%" in text
    assert "D 60%" in text


def test_briefing_skips_board_rules_as_failed_criteria():
    text = format_trajectory_briefing(
        TrajectorySnapshot(
            action="close_weak",
            reason="Закрой как слабую.",
            failed_criteria=[
                "discounted не падает при percent == 0.",
                "Если задача взята в работу, она доведена до закрытия.",
                "В письме о полном зачёте указана разовая премия 15000.",
            ],
        )
    )
    assert "percent == 0" in text
    assert "преми" not in text.lower()
    assert "доведена" not in text.lower()


def test_format_none_is_empty():
    assert format_trajectory_briefing(None) == ""


def test_chat_action_routes_to_sara():
    decision = route_without_llm("не понимаю, что не так", trajectory_action="chat")
    assert decision is not None
    assert decision.speaker.id == "sara"
    assert decision.source == "trajectory"


def test_mention_beats_trajectory_bias():
    decision = route_without_llm("Эмма, где баг?", trajectory_action="chat")
    assert decision is not None
    assert decision.speaker.id == "emma"
    assert decision.source == "mention"


def test_chat_prompt_includes_trajectory_briefing():
    skill = BuildChatPromptsSkill()
    briefing = format_trajectory_briefing(
        TrajectorySnapshot(
            action="chat",
            reason="Балл 4, разбери замечания.",
            current_score=4,
            current_attempts=1,
            failed_criteria=["Нет тестов"],
        )
    )

    async def _run() -> tuple[str, str]:
        return await skill.run(
            message="Как поправить?",
            chat_history=[],
            context={"task_title": "Валидация", "trajectory_briefing": briefing},
            knowledge_docs=[],
            member=SARA,
            briefing="",
            voice="user",
        )

    system, user = asyncio.run(_run())
    assert "Бриф траектории" in user
    assert "Нет тестов" in user
    assert "не предлагай закрыть задачу" in system.lower()


class _Memory:
    async def get_chat_history(self, session_id: str) -> list[Any]:
        return []

    async def append_chat_message(self, **kwargs: Any) -> None:
        return None

    async def save_document(self, text: str, metadata: dict[str, str]) -> None:
        return None


class _Orchestrator:
    def __init__(self) -> None:
        self.ctx: dict[str, object] | None = None

    async def run(self, message: str, chat_history: list[Any], user_context: Any) -> ChatTurnResult:
        self.ctx = user_context
        return ChatTurnResult(
            answer="ok",
            speaker_id="sara",
            speaker_name="Сара",
            speaker_role="Продакт",
            mode="solo",
        )

    async def cleanup_turn(self, message: str, user_context: Any) -> None:
        return None


class _Gateway:
    async def get_trajectory(self, authorization: str, task_id: int | None = None):
        assert authorization == "Bearer tok"
        assert task_id == 11
        return TrajectorySnapshot(
            action="chat",
            reason="Балл 4.",
            current_score=4,
            current_attempts=1,
            failed_criteria=["Нет тестов"],
        )


def test_use_case_skips_briefing_without_auth():
    orch = _Orchestrator()
    uc = ChatWithTeamUseCase(orch, _Memory(), trajectory_gateway=_Gateway())
    asyncio.run(uc(message="hi", session_id="s1"))
    assert orch.ctx is not None
    assert "trajectory_briefing" not in orch.ctx


def test_use_case_injects_briefing_from_gateway():
    orch = _Orchestrator()
    uc = ChatWithTeamUseCase(orch, _Memory(), trajectory_gateway=_Gateway())
    asyncio.run(uc(message="hi", session_id="s1", task_id=11, authorization="Bearer tok"))
    assert orch.ctx is not None
    assert "Следующий шаг" in str(orch.ctx.get("trajectory_briefing"))
    assert orch.ctx.get("trajectory_action") == "chat"
    assert orch.ctx.get("failed_criteria") == ["Нет тестов"]


def test_http_gateway_parses_trajectory():
    httpx = pytest.importorskip("httpx")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "trajectory" in str(request.url)
        assert request.url.params.get("task_id") == "7"
        return httpx.Response(
            200,
            json={
                "action": "chat",
                "reason": "Балл 4",
                "mastery": 0.4,
                "difficulty": 0.5,
                "pace": 0.2,
                "readiness": 0.4,
                "current_score": 4,
                "current_attempts": 1,
                "failed_criteria": ["Нет тестов"],
                "block_next_sprint": False,
                "block_close": True,
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = HttpTrajectoryGateway(
        SimpleNamespace(submission_gateway_settings=SimpleNamespace(url="http://submission")),
        client,
        SimpleNamespace(exception=lambda *a, **k: None, warning=lambda *a, **k: None),
    )
    snap = asyncio.run(gateway.get_trajectory("Bearer tok", task_id=7))
    assert snap is not None
    assert snap.action == "chat"
    assert snap.current_score == 4
    assert snap.failed_criteria == ["Нет тестов"]
    assert snap.block_close is True


def test_emma_session_is_one_speaker():
    decision = emma_session_route()
    assert decision.mode == "solo"
    assert decision.speaker.id == "emma"


def test_intern_turn_drops_huddle_to_one_speaker():
    decision = route_without_llm("баг в тесте и критерий приёмки")
    assert decision is not None and decision.mode == "huddle"
    solo = limit_to_one_speaker(decision)
    assert solo.mode == "solo"
    assert solo.speaker.id == decision.speaker.id
