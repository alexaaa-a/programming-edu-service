import asyncio
from typing import Any

import pytest

pytest.importorskip("langgraph")

from agent_service.app.application.dto import Review
from agent_service.app.application.graphs.review_graph import (
    REVIEW_GRAPH_NODES,
    compile_review_graph,
)
from agent_service.app.application.graphs.state import ChatState, ReviewState
from agent_service.app.application.orchestrators.review_orchestrator import ReviewOrchestrator
from agent_service.app.application.review.adversarial import ChallengeVerdict
from agent_service.app.application.tools.models import ToolReport


class _FakeToolkit:
    def __init__(self) -> None:
        self.calls = 0

    async def inspect(self, **kwargs: Any) -> ToolReport:
        self.calls += 1
        return ToolReport(language="python", syntax_ok=True, compile_ok=True)


class _FakeReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, code: str, task_description: str, tool_facts: str = "") -> Review:
        self.calls += 1
        return Review(score=8, feedback="ревью", suggestions=["уточни имя"])


class _FakeBug:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, code: str, tool_facts: str = "") -> Review:
        self.calls += 1
        return Review(score=8, feedback="баги", suggestions=[])


class _FakeMentor:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, code: str, results: Any, tool_facts: str = "") -> str:
        self.calls += 1
        return "Итог наставника: поправь имя функции."


class _FakeAdversarial:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, **kwargs: Any) -> ChallengeVerdict:
        self.calls += 1
        return ChallengeVerdict(agrees=True, severity="low")


def _orchestrator() -> tuple[ReviewOrchestrator, _FakeToolkit, _FakeAdversarial]:
    tools = _FakeToolkit()
    adversarial = _FakeAdversarial()
    orch = ReviewOrchestrator(
        reviewer_agent=_FakeReviewer(),
        bug_agent=_FakeBug(),
        mentor_agent=_FakeMentor(),
        adversarial_agent=adversarial,
        toolkit=tools,
        memory=None,
        llm=None,
        review_graph=compile_review_graph(),
    )
    return orch, tools, adversarial


def test_state_contracts_exist():
    review_keys = set(ReviewState.__annotations__)
    chat_keys = set(ChatState.__annotations__)
    assert {"code", "task_description", "tool_facts", "rubric", "review", "n_drafts"} <= review_keys
    assert {"message", "chat_history", "trajectory_action", "mode"} <= chat_keys


def test_review_graph_node_order():
    compiled = compile_review_graph()
    mermaid = compiled.get_graph().draw_mermaid()
    for name in REVIEW_GRAPH_NODES:
        assert name in mermaid
    assert mermaid.find("tools") < mermaid.find("finalize")
    assert "mentor_plan" in mermaid
    assert "mentor_single" in mermaid
    assert "mentor_multi" in mermaid


def test_full_graph_runs():
    async def _run() -> None:
        code = "def add(a, b):\n    return a + b\n"
        task = "- вернуть сумму двух чисел"
        orch, tools, adv = _orchestrator()
        review = await orch.run(code=code, task_description=task, submission_id="g1", attempt=1)
        assert tools.calls == 1
        assert adv.calls == 1
        names = [step.name for step in review.agent_path]
        for name in ("tools", "acceptance_rubric", "reviewer", "bug", "grade_rubric", "adversarial", "mentor", "process_eval"):
            assert name in names

    asyncio.run(_run())
