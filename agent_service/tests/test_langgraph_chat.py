import asyncio
from typing import Any

import pytest

pytest.importorskip("langgraph")

from agent_service.app.application.graphs.chat_graph import (
    CHAT_GRAPH_NODES,
    compile_chat_graph,
)
from agent_service.app.application.graphs.state import ChatState
from agent_service.app.application.orchestrators.chat_orchestrator import ChatOrchestrator
from agent_service.app.application.team import TeamMember
from agent_service.app.infrastructure.checkpoints import (
    InMemoryRunCheckpointStore,
    StoreBackedCheckpointSaver,
)
from agent_service.tests.test_langfuse_tracer import RecordingTracer


class _FakeChatAgent:
    def __init__(self, *, fail_user_once: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_user_once = fail_user_once

    async def speak(
            self,
            member: TeamMember,
            message: str,
            context: Any,
            chat_history: list[Any],
            briefing: str | None = None,
            voice: str = "user",
    ) -> str:
        self.calls.append((member.id, voice))
        if voice == "user" and self.fail_user_once:
            self.fail_user_once = False
            raise RuntimeError("crash after huddle notes")
        if voice == "internal":
            return f"заметка {member.id}"
        prefix = f"{member.id}"
        if briefing:
            return f"ответ {prefix} по брифу: {message[:60]}"
        return f"ответ {prefix}: {message[:60]}"


def _orchestrator(
        agent: _FakeChatAgent | None = None,
        checkpointer: StoreBackedCheckpointSaver | None = None,
        tracer: RecordingTracer | None = None,
) -> tuple[ChatOrchestrator, _FakeChatAgent]:
    fake = agent or _FakeChatAgent()
    orch = ChatOrchestrator(
        chat_agent=fake,
        llm=None,
        tracer=tracer,
        chat_graph=compile_chat_graph(checkpointer=checkpointer),
    )
    return orch, fake


def test_chat_state_has_graph_fields():
    keys = set(ChatState.__annotations__)
    assert {
        "message",
        "chat_history",
        "trajectory_action",
        "mode",
        "route_reason",
        "route_source",
        "result",
    } <= keys


def test_chat_graph_node_order():
    compiled = compile_chat_graph()
    mermaid = compiled.get_graph().draw_mermaid()
    for name in CHAT_GRAPH_NODES:
        assert name in mermaid
    assert mermaid.find("route") < mermaid.find("process_eval")
    assert mermaid.find("process_eval") < mermaid.find("finalize")
    assert "solo_speak" in mermaid
    assert "huddle_advisors" in mermaid


def test_solo_mention_emma():
    async def _run() -> None:
        message = "@эмма где падает валидация?"
        orch, agent = _orchestrator()
        turn = await orch.run(message=message, chat_history=[], user_context={})
        assert turn.mode == "solo"
        assert turn.speaker_id == "emma"
        assert turn.advisors == []
        assert agent.calls == [("emma", "user")]
        names = [step.name for step in turn.agent_path]
        for name in ("route", "speaker", "process_eval"):
            assert name in names
        assert "advisor" not in names

    asyncio.run(_run())


def test_huddle_keywords():
    async def _run() -> None:
        message = "критерии приёмки и баги на пустом вводе"
        orch, agent = _orchestrator()
        turn = await orch.run(message=message, chat_history=[], user_context={})
        assert turn.mode == "huddle"
        assert turn.speaker_id == "john"
        assert set(turn.advisors) == {"emma", "sara"}
        assert ("john", "user") in agent.calls
        assert {call[0] for call in agent.calls if call[1] == "internal"} == {"emma", "sara"}
        names = [step.name for step in turn.agent_path]
        for name in ("route", "advisor", "speaker", "process_eval"):
            assert name in names

    asyncio.run(_run())


def test_huddle_resume_skips_advisor_calls():
    async def _run() -> None:
        message = "критерии приёмки и баги на пустом вводе"
        context = {"session_id": "lg-chat-resume"}
        store = InMemoryRunCheckpointStore()
        agent = _FakeChatAgent(fail_user_once=True)
        orch1, _ = _orchestrator(
            agent=agent,
            checkpointer=StoreBackedCheckpointSaver(store),
        )
        with pytest.raises(RuntimeError, match="crash after huddle notes"):
            await orch1.run(message=message, chat_history=[], user_context=context)
        tracer = RecordingTracer()
        orch2, _ = _orchestrator(
            agent=agent,
            checkpointer=StoreBackedCheckpointSaver(store),
            tracer=tracer,
        )
        turn = await orch2.run(message=message, chat_history=[], user_context=context)
        assert turn.mode == "huddle"
        assert turn.speaker_id == "john"
        assert set(turn.advisors) == {"emma", "sara"}
        assert agent.calls.count(("john", "user")) == 2
        assert {call[0] for call in agent.calls if call[1] == "internal"} == {"emma", "sara"}
        assert "huddle_advisors" not in tracer.names
        assert "huddle_speak" in tracer.names

    asyncio.run(_run())


def test_trajectory_chat_routes_to_sara_on_graph():
    async def _run() -> None:
        orch, agent = _orchestrator()
        turn = await orch.run(
            message="не понимаю, что не так",
            chat_history=[],
            user_context={"trajectory_action": "chat"},
        )
        assert turn.mode == "solo"
        assert turn.speaker_id == "sara"
        assert agent.calls == [("sara", "user")]

    asyncio.run(_run())
