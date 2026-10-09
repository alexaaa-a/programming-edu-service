"""Чтение графа в конвейере ревью и в чате, с откатом на проекцию."""

import asyncio
from datetime import datetime, timedelta, timezone

from agent_service.app.application.dto.student_profile import StudentProfile
from agent_service.app.application.graph_memory.facts import (
    FactTarget,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.graph_briefing import graph_briefing
from agent_service.app.application.graph_memory.ontology import EXHIBITS, STRUGGLES_WITH
from agent_service.app.application.graph_memory.recipes import (
    ReadIntent,
    intent_question,
    intent_state,
    read_intent,
)
from agent_service.app.application.decisions.questions import Answers, ChoiceAnswer
from agent_service.app.application.tools.graph_facts import (
    as_findings,
    load_graph_facts,
    skills_of_task,
)
from agent_service.app.application.tools.toolkit import ReviewToolkit


NOW = datetime.now(tz=timezone.utc)


def _fact(
        relation: str = EXHIBITS,
        kind: str = "error_pattern",
        key: str = "bare_except",
        occurrences: int = 4,
        source: SourceKind = SourceKind.HIDDEN_TESTS,
        age_days: float = 2.0,
) -> StoredFact:
    seen = NOW - timedelta(days=age_days)
    return StoredFact(
        edge_uuid=f"e-{key}",
        user_id="u1",
        relation=relation,
        target=FactTarget(kind, key, key.replace("_", " ")),
        statement="The student catches every exception with a bare except.",
        source=source,
        confidence=0.9,
        occurred_at=seen,
        created_at=seen,
        last_seen_at=seen,
        occurrences=occurrences,
    )


class StubGraph:
    def __init__(self, facts=None, enabled: bool = True, failing: bool = False) -> None:
        self._facts = list(facts or [])
        self._enabled = enabled
        self._failing = failing
        self.calls: list[dict] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def facts_for(self, user_id, intent, query="", skill_ids=(), limit=None):
        self.calls.append({"intent": intent, "query": query, "skills": list(skill_ids)})
        if self._failing:
            raise RuntimeError("neo4j is down")
        return list(self._facts)

    async def all_facts(self, user_id, include_closed=False):
        return list(self._facts)


class StubMemory:
    async def retrieve(self, query, k=4, types=None, scope=None):
        return []

    async def save_document(self, text, metadata):
        return None


class StubProfiles:
    def __init__(self, facts: list[str]) -> None:
        self._facts = facts

    async def get(self, user_id: str):
        return StudentProfile(user_id=user_id, facts=list(self._facts), updated_at=NOW)

    async def save(self, user_id, facts, task_id=None):
        return None


def test_findings_carry_provenance_and_mark_repeats():
    findings = as_findings([_fact()])
    assert len(findings) == 1
    message = findings[0].message

    assert "повторяется ×4" in message
    assert "подтверждено прогоном тестов" in message
    # Хроническая ошибка заметнее обычной находки.
    assert findings[0].severity == "warn"


def test_task_text_picks_the_anchor_skill():
    assert skills_of_task("Нужно корректно обрабатывать исключения") == ["error_handling"]
    assert skills_of_task("") == []


def test_graph_read_centres_on_the_task_skill():
    async def _run() -> None:
        graph = StubGraph([_fact()])
        await load_graph_facts(graph, "u1", task_description="обработка исключений", task_id="t1")
        call = graph.calls[0]
        assert call["intent"] is ReadIntent.TASK_CONTEXT
        assert call["skills"] == ["error_handling"]

    asyncio.run(_run())


def test_graph_read_is_silent_when_disabled_or_broken():
    async def _run() -> None:
        assert await load_graph_facts(StubGraph(enabled=False), "u1") == []
        assert await load_graph_facts(None, "u1") == []
        assert await load_graph_facts(StubGraph([_fact()]), None) == []
        assert await load_graph_facts(StubGraph(failing=True), "u1") == []

    asyncio.run(_run())


def test_toolkit_prefers_the_graph():
    async def _run() -> None:
        toolkit = ReviewToolkit(
            StubMemory(),
            profiles=StubProfiles(["старая плоская заметка"]),
            graph=StubGraph([_fact()]),
        )
        report = await toolkit.inspect("print(1)", "обработка исключений", task_id="t1", user_id="u1")
        messages = [finding.message for finding in report.findings]

        assert any("Память команды" in message for message in messages)
        assert not any("старая плоская заметка" in message for message in messages)

    asyncio.run(_run())


def test_toolkit_falls_back_to_the_flat_profile():
    async def _run() -> None:
        toolkit = ReviewToolkit(
            StubMemory(),
            profiles=StubProfiles(["глотает ошибки голым except"]),
            graph=StubGraph([], enabled=True),
        )
        report = await toolkit.inspect("print(1)", "обработка исключений", task_id="t1", user_id="u1")
        messages = [finding.message for finding in report.findings]

        # Граф пуст — работает ровно то поведение, что было до графа.
        assert any("глотает ошибки голым except" in message for message in messages)

    asyncio.run(_run())


def test_toolkit_without_graph_keeps_old_behaviour():
    async def _run() -> None:
        toolkit = ReviewToolkit(
            StubMemory(),
            profiles=StubProfiles(["слабая валидация входа"]),
        )
        report = await toolkit.inspect("print(1)", "валидация", task_id="t1", user_id="u1")
        assert any("слабая валидация входа" in finding.message for finding in report.findings)

    asyncio.run(_run())


def test_chat_briefing_is_short_and_marked_as_memory():
    async def _run() -> None:
        text = await graph_briefing(
            StubGraph([_fact()]),
            user_id="u1",
            message="почему тесты падают?",
            task_title="Orders API",
            focus_skill="error_handling",
        )
        assert text.startswith("Память команды об этом студенте:")
        assert "повторяется ×4" in text
        # Явная рамка: это память, а не условие задачи.
        assert "не условие задачи" in text

    asyncio.run(_run())


def test_chat_briefing_is_empty_without_facts():
    async def _run() -> None:
        assert await graph_briefing(StubGraph([]), "u1", "привет") == ""
        assert await graph_briefing(StubGraph([_fact()], enabled=False), "u1", "привет") == ""
        assert await graph_briefing(None, "u1", "привет") == ""

    asyncio.run(_run())


def test_read_intent_is_a_closed_choice():
    question = intent_question()
    assert set(question.options) == {
        ReadIntent.CHAT_CONTEXT.value,
        ReadIntent.TASK_CONTEXT.value,
        ReadIntent.SKILL_HISTORY.value,
    }

    confident = Answers(items={"memory_intent": ChoiceAnswer("skill_history", 0.9, {})})
    assert read_intent(confident, min_confidence=0.6) is ReadIntent.SKILL_HISTORY

    unsure = Answers(items={"memory_intent": ChoiceAnswer("skill_history", 0.2, {})})
    assert read_intent(unsure, min_confidence=0.6) is ReadIntent.CHAT_CONTEXT

    invented = Answers(items={"memory_intent": ChoiceAnswer("read_everything", 0.99, {})})
    assert read_intent(invented, min_confidence=0.6) is ReadIntent.CHAT_CONTEXT

    assert intent_state("сообщение", "задача", "testing")["focus_skill"] == "testing"


def test_struggle_without_repeats_is_plain_info():
    findings = as_findings([_fact(relation=STRUGGLES_WITH, kind="skill", key="testing", occurrences=1)])
    assert findings[0].severity == "info"
    assert "повторяется" not in findings[0].message
