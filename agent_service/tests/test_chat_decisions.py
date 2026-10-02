import asyncio
from typing import Any

import pytest

pytest.importorskip("langgraph")

from agent_service.app.application.decisions.policies import chat_turn_questions
from agent_service.app.application.decisions.questions import Answers, parse_answers
from agent_service.app.application.graphs.chat_graph import compile_chat_graph
from agent_service.app.application.orchestrators.chat_orchestrator import ChatOrchestrator
from agent_service.app.application.skills.standard_skills import BuildChatPromptsSkill
from agent_service.app.application.team import EMMA, TeamMember


class _FakeChatAgent:
    def __init__(self) -> None:
        self.contexts: list[Any] = []

    async def speak(
            self,
            member: TeamMember,
            message: str,
            context: Any,
            chat_history: list[Any],
            briefing: str | None = None,
            voice: str = "user",
    ) -> str:
        self.contexts.append(context)
        return f"ответ {member.id}"


class _Decisions:
    def __init__(self, answers: Answers, enabled: bool = True) -> None:
        self._answers = answers
        self._enabled = enabled
        self.states: list[Any] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ask(self, state, questions, label: str = "") -> Answers:
        self.states.append(state)
        return self._answers


def _answers(
        speaker: str = "emma",
        confidence: float = 0.9,
        huddle: float = 0.1,
        solution_seeking: float = 0.1,
        frustration: float = 0.0,
) -> Answers:
    probabilities = {"sara": 0.02, "mike": 0.02, "emma": 0.02, "john": 0.02}
    probabilities[speaker] = confidence
    body = {
        "answers": {
            "speaker": {
                "type": "choice",
                "choice": speaker,
                "confidence": confidence,
                "probabilities": probabilities,
            },
            "huddle": {"type": "noul", "noul": huddle},
            "solution_seeking": {"type": "noul", "noul": solution_seeking},
            "frustration": {"type": "score", "score": frustration, "confidence": 0.9},
        }
    }
    return parse_answers(body, chat_turn_questions())


def _orchestrator(decisions: _Decisions | None) -> tuple[ChatOrchestrator, _FakeChatAgent]:
    agent = _FakeChatAgent()
    return (
        ChatOrchestrator(
            chat_agent=agent,
            llm=None,
            chat_graph=compile_chat_graph(),
            decisions=decisions,
            min_confidence=0.6,
        ),
        agent,
    )


def _run(orchestrator: ChatOrchestrator, message: str, context: dict[str, Any]):
    return asyncio.run(
        orchestrator.run(message=message, chat_history=[], user_context=context)
    )


def test_decision_model_routes_the_turn_without_an_llm_call():
    decisions = _Decisions(_answers(speaker="emma", confidence=0.93))
    orchestrator, _ = _orchestrator(decisions)
    context = {"session_id": "s1", "user_id": "7", "task_title": "Пагинация заказов"}

    result = _run(orchestrator, "после деплоя ручка стала отдавать 500", context)

    assert result.speaker_id == EMMA.id
    assert result.mode == "solo"
    steps = {step.name: step.detail for step in result.agent_path}
    assert "source=decisions" in steps["route"]
    # состояние для модели — данные хода, а не промпт
    assert decisions.states[0]["task_title"] == "Пагинация заказов"


def test_high_huddle_probability_turns_the_turn_into_a_huddle():
    decisions = _Decisions(_answers(speaker="john", confidence=0.8, huddle=0.9))
    orchestrator, _ = _orchestrator(decisions)
    result = _run(orchestrator, "надо решить, как резать модуль и кто проверит", {})
    assert result.mode == "huddle" and result.speaker_id == "john"


def test_name_in_the_message_beats_the_model():
    decisions = _Decisions(_answers(speaker="sara", confidence=0.99))
    orchestrator, _ = _orchestrator(decisions)
    result = _run(orchestrator, "Эмма, глянь падение теста", {})
    assert result.speaker_id == EMMA.id
    steps = {step.name: step.detail for step in result.agent_path}
    assert "source=mention" in steps["route"]


def test_unavailable_model_falls_back_to_keywords():
    decisions = _Decisions(Answers.unavailable("transport_error"))
    orchestrator, _ = _orchestrator(decisions)
    result = _run(orchestrator, "падает тест на пустом списке", {})
    steps = {step.name: step.detail for step in result.agent_path}
    assert "source=keywords" in steps["route"]
    assert result.speaker_id == EMMA.id


def test_no_model_at_all_keeps_the_old_path():
    orchestrator, _ = _orchestrator(None)
    result = _run(orchestrator, "как лучше разложить модули", {})
    steps = {step.name: step.detail for step in result.agent_path}
    assert "source=keywords" in steps["route"]
    assert all(step.name != "coach" for step in result.agent_path)


def test_solution_seeking_and_frustration_reach_the_speaker_prompt():
    decisions = _Decisions(
        _answers(speaker="john", confidence=0.8, solution_seeking=0.95, frustration=3.0)
    )
    orchestrator, agent = _orchestrator(decisions)
    context: dict[str, Any] = {"session_id": "s1", "user_id": "7"}

    result = _run(orchestrator, "скинь просто готовый код, я устал", context)

    coach = context["coach"]
    assert any("Готовый код" in line for line in coach)
    assert any("Один шаг" in line for line in coach)
    assert agent.contexts[0] is context
    detail = {step.name: step.detail for step in result.agent_path}["coach"]
    assert detail == "solution_seeking=1,frustration=3"


def test_prompt_builder_renders_the_coach_block():
    async def _run_prompt() -> tuple[str, str]:
        return await BuildChatPromptsSkill().run(
            message="дай код",
            chat_history=[],
            context={"coach": ["Готовый код не выдавай.", "Один шаг на ответ."]},
            knowledge_docs=[],
            member=EMMA,
        )

    system_prompt, _ = asyncio.run(_run_prompt())
    assert "Готовый код не выдавай." in system_prompt
    assert "Один шаг на ответ." in system_prompt


def test_coach_block_is_absent_without_a_policy():
    async def _run_prompt() -> tuple[str, str]:
        return await BuildChatPromptsSkill().run(
            message="привет",
            chat_history=[],
            context={"task_title": "Задача"},
            knowledge_docs=[],
            member=EMMA,
        )

    system_prompt, _ = asyncio.run(_run_prompt())
    assert "Готовый код не выдавай" not in system_prompt
