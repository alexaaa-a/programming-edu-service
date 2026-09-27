import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_service.app.application.graphs.runner import ainvoke_graph
from agent_service.app.application.tools.past_reviews import load_past_reviews
from agent_service.app.application.tools.sandbox import compile_javascript
from agent_service.app.application.tools.toolkit import ReviewToolkit
from agent_service.app.application.agents.chat_agent import ChatAgent
from agent_service.app.application.dto.rag import RetrievedDocument


class _Doc:
    def __init__(self, text: str, metadata: dict[str, Any]) -> None:
        self.text = text
        self.metadata = metadata


class _Memory:
    def __init__(self, docs: list[_Doc]) -> None:
        self.docs = docs
        self.queries: list[dict[str, Any]] = []

    async def retrieve(self, query: str, k: int = 4, types: set[str] | None = None):
        self.queries.append({"query": query, "k": k, "types": types})
        return list(self.docs)

    async def save_document(self, text: str, metadata: dict) -> None:
        return None


def test_past_reviews_require_user_id_and_filter():
    async def _run() -> None:
        memory = _Memory(
            [
                _Doc("mine", {"type": "past_review", "user_id": "u1", "task_id": "t1"}),
                _Doc("other", {"type": "past_review", "user_id": "u2", "task_id": "t1"}),
                _Doc("wrong-task", {"type": "past_review", "user_id": "u1", "task_id": "t9"}),
            ]
        )
        assert await load_past_reviews(memory, "desc", task_id="t1", user_id=None) == []
        assert await load_past_reviews(memory, "desc", task_id=None, user_id="u1") == []
        hits = await load_past_reviews(memory, "desc", task_id="t1", user_id="u1")
        assert len(hits) == 1
        assert "mine" in hits[0].message
        assert "other" not in hits[0].message
        assert "wrong-task" not in hits[0].message

    asyncio.run(_run())


def test_compile_javascript_fail_closed_without_node():
    async def _run() -> None:
        with patch("agent_service.app.application.tools.sandbox.shutil.which", return_value=None):
            finding = await compile_javascript("const x = 1;")
        assert finding is not None
        assert finding.severity == "error"
        assert "node" in finding.message.lower()

    asyncio.run(_run())


def test_toolkit_sets_compile_ok_false_when_node_missing():
    async def _run() -> None:
        toolkit = ReviewToolkit(_Memory([]))
        with patch(
            "agent_service.app.application.tools.toolkit.compile_javascript",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    tool="sandbox",
                    severity="error",
                    message="JS проверка недоступна: node не найден в окружении",
                )
            ),
        ):
            with patch(
                "agent_service.app.application.tools.toolkit.detect_language",
                return_value="javascript",
            ), patch(
                "agent_service.app.application.tools.toolkit.analyze_code",
                return_value=(True, []),
            ):
                report = await toolkit.inspect("const x = 1;", "task", user_id="u1")
        assert report.compile_ok is False

    asyncio.run(_run())


def test_ainvoke_graph_does_not_swallow_aget_state_errors():
    async def _run() -> None:
        class BoomGraph:
            checkpointer = object()

            async def aget_state(self, config):
                raise RuntimeError("redis down")

            async def ainvoke(self, *args, **kwargs):
                raise AssertionError("must not ainvoke after aget_state failure")

        with pytest.raises(RuntimeError, match="redis down"):
            await ainvoke_graph(
                BoomGraph(),
                {"x": 1},
                context=None,
                thread_id="t1",
                graph_name="review",
            )

    asyncio.run(_run())


def test_ainvoke_graph_reuses_terminal_checkpoint():
    async def _run() -> None:
        class DoneGraph:
            checkpointer = object()

            async def aget_state(self, config):
                return SimpleNamespace(next=(), values={"review": "done-review", "path": []})

            async def ainvoke(self, *args, **kwargs):
                raise AssertionError("must not re-run finished graph")

        out = await ainvoke_graph(
            DoneGraph(),
            {"code": "x"},
            context=None,
            thread_id="t-done",
            graph_name="review",
        )
        assert out["review"] == "done-review"

    asyncio.run(_run())


def test_chat_docs_scoped_by_user():
    agent = ChatAgent(llm=AsyncMock(), memory=AsyncMock())  # type: ignore[arg-type]
    docs = [
        RetrievedDocument("mine", {"type": "chat_episode", "user_id": "7", "session_id": "s1"}),
        RetrievedDocument("other", {"type": "chat_episode", "user_id": "9", "session_id": "s1"}),
        RetrievedDocument("orphan", {"type": "chat_episode", "session_id": "s1"}),
        RetrievedDocument("semantic", {"type": "best_practice"}),
        RetrievedDocument("leak", {"type": "past_review", "user_id": "9"}),
    ]
    scoped = agent._scope_docs(docs, context={"user_id": "7", "session_id": "s1"})
    texts = [d.text for d in scoped]
    assert texts == ["mine", "semantic"]
