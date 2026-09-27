import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from agent_service.app.application.orchestrators.chat_orchestrator import chat_graph_thread_id
from agent_service.app.application.use_cases.chat_with_team import ChatWithTeamUseCase
from agent_service.app.application.dto.chat import ChatTurnResult, PathStepResult


class _Mem:
    def __init__(self) -> None:
        self.history: list[Any] = []
        self.docs: list[dict[str, Any]] = []

    async def get_chat_history(self, session_id: str):
        return list(self.history)

    async def append_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        turn_id: str | None = None,
    ):
        self.history.append(SimpleNamespace(role=role, content=content, turn_id=turn_id))

    async def save_document(self, text: str, metadata: dict) -> None:
        self.docs.append({"text": text, "metadata": dict(metadata)})


def test_concurrent_identical_chat_turns_get_distinct_thread_ids():
    a = chat_graph_thread_id("hi", {"user_id": "1", "session_id": "s", "turn_id": "t-a"})
    b = chat_graph_thread_id("hi", {"user_id": "1", "session_id": "s", "turn_id": "t-b"})
    assert a != b
    same = chat_graph_thread_id("hi", {"user_id": "1", "session_id": "s", "turn_id": "t-a"})
    assert a == same


def test_chat_use_case_mints_unique_turn_ids_by_default():
    orch = AsyncMock()
    orch.run = AsyncMock(
        return_value=ChatTurnResult(
            answer="ok",
            speaker_id="emma",
            speaker_name="Emma",
            speaker_role="Team Lead",
            mode="solo",
            advisors=[],
            agent_path=[PathStepResult(kind="step", name="route", status="ok")],
        )
    )
    mem = _Mem()
    uc = ChatWithTeamUseCase(orchestrator=orch, memory=mem)  # type: ignore[arg-type]

    async def _run() -> None:
        await uc(message="hello", session_id="s1", user_id="7")
        await uc(message="hello", session_id="s1", user_id="7")
        turn_ids = [call.kwargs["user_context"]["turn_id"] for call in orch.run.await_args_list]
        assert len(turn_ids) == 2
        assert turn_ids[0] != turn_ids[1]

    asyncio.run(_run())


def test_chat_episode_id_includes_user_id():
    orch = AsyncMock()
    from agent_service.app.application.dto.chat import ChatTurnResult

    orch.run = AsyncMock(
        return_value=ChatTurnResult(
            answer="ok",
            speaker_id="emma",
            speaker_name="Emma",
            speaker_role="Team Lead",
            mode="solo",
            advisors=[],
            agent_path=[],
        )
    )
    mem = _Mem()
    uc = ChatWithTeamUseCase(orchestrator=orch, memory=mem)  # type: ignore[arg-type]

    async def _run() -> None:
        await uc(message="q", session_id="shared", user_id="42")
        assert mem.docs
        doc_id = mem.docs[0]["metadata"]["id"]
        assert doc_id.startswith("chat_episode_42_shared_")
        assert mem.docs[0]["metadata"]["user_id"] == "42"

    asyncio.run(_run())


def test_chat_resume_reuses_client_turn_id():
    orch = AsyncMock()
    from agent_service.app.application.dto.chat import ChatTurnResult

    orch.run = AsyncMock(
        return_value=ChatTurnResult(
            answer="ok",
            speaker_id="emma",
            speaker_name="Emma",
            speaker_role="Team Lead",
            mode="solo",
            advisors=[],
            agent_path=[],
        )
    )
    mem = _Mem()
    uc = ChatWithTeamUseCase(orchestrator=orch, memory=mem)  # type: ignore[arg-type]

    async def _run() -> None:
        await uc(message="hello", session_id="s1", user_id="7", turn_id="stable-turn")
        assert orch.run.await_args.kwargs["user_context"]["turn_id"] == "stable-turn"

    asyncio.run(_run())
