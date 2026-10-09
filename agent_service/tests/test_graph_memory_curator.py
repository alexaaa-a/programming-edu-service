"""Хранитель памяти и фоновые рабочие."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from agent_service.app.application.decisions.questions import Answers, ChoiceAnswer
from agent_service.app.application.graph_memory.consolidation import ConsolidationPlan
from agent_service.app.application.graph_memory.curator import MemoryCurator
from agent_service.app.application.graph_memory.facts import (
    EpisodeKind,
    FactOperation,
    FactTarget,
    GraphFact,
    GraphWriteResult,
    MemoryEpisode,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    STRUGGLES_WITH,
    WORKED_ON,
)
from agent_service.app.infrastructure.graph_memory.workers import (
    MemoryConsolidationWorker,
    MemoryIngestWorker,
)


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _closed(fact: StoredFact, at: datetime) -> StoredFact:
    return StoredFact(
        edge_uuid=fact.edge_uuid,
        user_id=fact.user_id,
        relation=fact.relation,
        target=fact.target,
        statement=fact.statement,
        source=fact.source,
        confidence=fact.confidence,
        occurred_at=fact.occurred_at,
        created_at=fact.created_at,
        valid_until=at,
        occurrences=fact.occurrences,
        last_seen_at=fact.last_seen_at,
    )


class FakeGraph:
    """Граф в памяти: хранит факты списком и считает вызовы."""

    def __init__(self, facts: list[StoredFact] | None = None, enabled: bool = True) -> None:
        self._facts = list(facts or [])
        self._enabled = enabled
        self.written: list[GraphFact] = []
        self.invalidated: list[tuple[str, str]] = []
        self.updated: list[tuple[str, float, bool]] = []
        self.merged: list[tuple[str, str]] = []
        self.mastery: dict[str, dict[str, float]] = {}
        self.forgotten: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ensure_schema(self) -> None:
        return None

    async def write(self, fact: GraphFact) -> GraphWriteResult:
        self.written.append(fact)
        edge_uuid = f"edge-{len(self.written)}"
        # Фейк действительно хранит записанное: иначе проекция, которая
        # перечитывает граф, в тестах всегда была бы пустой.
        self._facts.append(
            StoredFact(
                edge_uuid=edge_uuid,
                user_id=fact.user_id,
                relation=fact.relation,
                target=fact.target,
                statement=fact.statement,
                source=fact.source,
                confidence=fact.confidence,
                occurred_at=fact.occurred_at,
                created_at=fact.occurred_at,
                last_seen_at=fact.occurred_at,
            )
        )
        return GraphWriteResult(fact.operation, edge_uuid=edge_uuid)

    async def invalidate(self, fact: StoredFact, at: datetime, reason: str = "") -> bool:
        self.invalidated.append((fact.edge_uuid, reason))
        self._facts = [
            item if item.edge_uuid != fact.edge_uuid else _closed(item, at)
            for item in self._facts
        ]
        return True

    async def update_confidence(self, fact: StoredFact, confidence: float, chronic: bool = False) -> bool:
        self.updated.append((fact.edge_uuid, confidence, chronic))
        return True

    async def merge_facts(self, keep: StoredFact, drop: StoredFact, occurrences: int) -> bool:
        self.merged.append((keep.edge_uuid, drop.edge_uuid))
        return True

    async def facts_for(self, user_id, intent, query="", skill_ids=(), limit=None) -> list[StoredFact]:
        return list(self._facts)

    async def all_facts(self, user_id: str, include_closed: bool = False) -> list[StoredFact]:
        if include_closed:
            return list(self._facts)
        return [fact for fact in self._facts if fact.is_valid]

    async def known_pattern_slugs(self, user_id: str) -> list[str]:
        return [fact.target.key for fact in self._facts if fact.target.kind == "error_pattern"]

    async def remember_mastery(self, user_id: str, mastery: dict[str, float]) -> None:
        self.mastery[user_id] = dict(mastery)

    async def mastery_of(self, user_id: str) -> dict[str, float]:
        return dict(self.mastery.get(user_id, {}))

    async def students_with_memory(self, limit: int = 200) -> list[str]:
        return ["u1"]

    async def forget_student(self, user_id: str) -> int:
        self.forgotten.append(user_id)
        return 1


class FakeLLM:
    def __init__(self, reply: str = "[]") -> None:
        self.reply = reply
        self.calls = 0

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return self.reply


class FakeDecisions:
    def __init__(self, answers: Answers | None = None, enabled: bool = True) -> None:
        self._answers = answers if answers is not None else Answers(items={})
        self._enabled = enabled
        self.labels: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ask(self, state, questions, label: str = "") -> Answers:
        self.labels.append(label)
        return self._answers


class FakeProfiles:
    def __init__(self) -> None:
        self.saved: list[tuple[str, list[str]]] = []

    async def get(self, user_id: str):
        return None

    async def save(self, user_id: str, facts: list[str], task_id: str | None = None) -> None:
        self.saved.append((user_id, list(facts)))


class FakeQueue:
    def __init__(self, episodes: Sequence[MemoryEpisode] = ()) -> None:
        self.pending = list(episodes)
        self.done: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def enqueue(self, episode: MemoryEpisode) -> bool:
        self.pending.append(episode)
        return True

    async def claim(self, limit: int, now: datetime | None = None) -> list[MemoryEpisode]:
        taken, self.pending = self.pending[:limit], self.pending[limit:]
        return taken

    async def mark_done(self, episode_id: str, facts_written: int = 0) -> None:
        self.done.append(episode_id)

    async def mark_failed(self, episode_id: str, reason: str) -> None:
        self.failed.append((episode_id, reason))

    async def pending_count(self) -> int:
        return len(self.pending)


def _review_episode(**overrides: Any) -> MemoryEpisode:
    base: dict[str, Any] = {
        "episode_id": "ep1",
        "kind": EpisodeKind.REVIEW,
        "user_id": "u1",
        "occurred_at": NOW,
        "body": "Score: 4/10",
        "task_id": "t1",
        "submission_id": "s1",
        "task_title": "Orders API",
        "observations": [
            {"kind": "criterion", "passed": False, "text": "Исключения не проглатываются"},
            {"kind": "hidden_tests", "status": "failed", "total": 5, "passed": 2, "failed_names": []},
        ],
    }
    base.update(overrides)
    return MemoryEpisode(**base)


def _stored(relation: str, kind: str, key: str, source: SourceKind) -> StoredFact:
    return StoredFact(
        edge_uuid=f"{relation}-{key}",
        user_id="u1",
        relation=relation,
        target=FactTarget(kind, key, key),
        statement="stored",
        source=source,
        confidence=0.8,
        occurred_at=NOW - timedelta(days=3),
        created_at=NOW - timedelta(days=3),
        last_seen_at=NOW - timedelta(days=3),
    )


def test_curator_writes_rule_based_facts_without_any_model():
    async def _run() -> None:
        graph = FakeGraph()
        curator = MemoryCurator(graph=graph, llm=None, decisions=None, model_extraction_enabled=False)
        result = await curator.curate(_review_episode())

        keys = {(fact.relation, fact.target.key) for fact in graph.written}
        assert (STRUGGLES_WITH, "error_handling") in keys
        assert (WORKED_ON, "t1") in keys
        assert result.added >= 2
        assert result.model_facts == 0

    asyncio.run(_run())


def test_curator_skips_everything_when_graph_is_off():
    async def _run() -> None:
        graph = FakeGraph(enabled=False)
        llm = FakeLLM()
        curator = MemoryCurator(graph=graph, llm=llm)
        result = await curator.curate(_review_episode())

        assert result.written == 0
        assert graph.written == []
        # Выключённый граф не должен стоить ни одного обращения к модели.
        assert llm.calls == 0

    asyncio.run(_run())


def test_curator_uses_model_facts_and_anchors_them():
    async def _run() -> None:
        graph = FakeGraph()
        llm = FakeLLM(
            '[{"relation": "EXHIBITS", "target_kind": "error_pattern", '
            '"target_key": "bare_except", "statement": "The student keeps using a bare except.", '
            '"confidence": 0.85}]'
        )
        curator = MemoryCurator(graph=graph, llm=llm, decisions=None)
        result = await curator.curate(_review_episode())

        assert llm.calls == 1
        assert result.model_facts == 1
        assert any(fact.target.key == "bare_except" for fact in graph.written)

    asyncio.run(_run())


def test_decision_model_can_veto_a_fact():
    async def _run() -> None:
        graph = FakeGraph()
        # Все факты «не стоит хранить».
        answers = Answers(items={f"keep_{index}": 0.1 for index in range(6)})
        curator = MemoryCurator(
            graph=graph,
            llm=None,
            decisions=FakeDecisions(answers),
            model_extraction_enabled=False,
        )
        result = await curator.curate(_review_episode())

        assert graph.written == []
        assert result.skipped >= 2

    asyncio.run(_run())


def test_decision_model_cannot_close_a_stronger_fact():
    """Ворота выбирают операцию, но домен проверяет право её применить."""
    async def _run() -> None:
        held = _stored(STRUGGLES_WITH, "skill", "error_handling", SourceKind.HIDDEN_TESTS)
        graph = FakeGraph([held])
        answers = Answers(
            items={
                **{f"keep_{index}": 0.95 for index in range(6)},
                **{f"op_{index}": ChoiceAnswer("invalidate", 0.99, {}) for index in range(6)},
            }
        )
        episode = _review_episode(
            kind=EpisodeKind.CHAT,
            observations=[],
            body="Student: я теперь всегда обрабатываю ошибки",
            session_id="sess1",
        )
        llm = FakeLLM(
            '[{"relation": "DEMONSTRATES", "target_kind": "skill", "target_key": "error_handling", '
            '"statement": "The student now handles errors correctly.", "confidence": 0.9}]'
        )
        curator = MemoryCurator(graph=graph, llm=llm, decisions=FakeDecisions(answers))
        result = await curator.curate(episode)

        # Слова в чате не закрывают то, что показал прогон тестов.
        assert graph.invalidated == []
        assert result.invalidated == 0
        assert result.skipped >= 1

    asyncio.run(_run())


def test_execution_closes_a_pattern_and_refreshes_projection():
    async def _run() -> None:
        held = _stored(EXHIBITS, "error_pattern", "bare_except", SourceKind.REVIEW)
        graph = FakeGraph([held])
        episode = _review_episode(
            observations=[
                {"kind": "criterion", "passed": True, "text": "Исключения обработаны"},
                {"kind": "hidden_tests", "status": "passed", "total": 5, "passed": 5},
            ],
        )
        curator = MemoryCurator(graph=graph, llm=None, decisions=None, model_extraction_enabled=False)
        result = await curator.curate(episode)

        assert ("EXHIBITS-bare_except", "resolved") in graph.invalidated
        assert result.invalidated == 1
        # После записи проекция пересобирается — это запасной путь чтения.
        assert result.profile

    asyncio.run(_run())


def test_mastery_snapshot_lands_on_the_graph():
    async def _run() -> None:
        graph = FakeGraph()
        curator = MemoryCurator(graph=graph, llm=None, decisions=None, model_extraction_enabled=False)
        await curator.curate(_review_episode(mastery={"error_handling": 0.42}))
        assert graph.mastery["u1"] == {"error_handling": 0.42}

    asyncio.run(_run())


def test_curator_survives_a_broken_model():
    async def _run() -> None:
        class Broken:
            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                raise RuntimeError("model down")

        graph = FakeGraph()
        curator = MemoryCurator(graph=graph, llm=Broken(), decisions=None)
        result = await curator.curate(_review_episode())

        # Правила отработали, несмотря на упавшую модель.
        assert result.added >= 2

    asyncio.run(_run())


def test_ingest_worker_drains_the_queue_and_saves_projection():
    async def _run() -> None:
        graph = FakeGraph()
        profiles = FakeProfiles()
        queue = FakeQueue([_review_episode()])
        worker = MemoryIngestWorker(
            queue=queue,
            curator=MemoryCurator(graph=graph, llm=None, decisions=None, model_extraction_enabled=False),
            graph=graph,
            profiles=profiles,
        )
        handled = await worker.run_once()

        assert handled == 1
        assert queue.done == ["ep1"]
        assert profiles.saved and profiles.saved[0][0] == "u1"

    asyncio.run(_run())


def test_ingest_worker_returns_a_broken_episode_to_the_queue():
    async def _run() -> None:
        class BrokenCurator(MemoryCurator):
            async def curate(self, episode):
                raise RuntimeError("graph down")

        graph = FakeGraph()
        queue = FakeQueue([_review_episode()])
        worker = MemoryIngestWorker(
            queue=queue,
            curator=BrokenCurator(graph=graph),
            graph=graph,
        )
        await worker.run_once()

        assert queue.done == []
        assert queue.failed and "graph down" in queue.failed[0][1]

    asyncio.run(_run())


def test_consolidation_worker_applies_the_plan():
    async def _run() -> None:
        stale = StoredFact(
            edge_uuid="old",
            user_id="u1",
            relation=EXHIBITS,
            target=FactTarget("error_pattern", "old_habit", "old habit"),
            statement="The student used to do this.",
            source=SourceKind.REVIEW,
            confidence=0.4,
            occurred_at=NOW - timedelta(days=400),
            created_at=NOW - timedelta(days=400),
            last_seen_at=NOW - timedelta(days=400),
        )
        graph = FakeGraph([stale])
        profiles = FakeProfiles()
        worker = MemoryConsolidationWorker(
            graph=graph,
            profiles=profiles,
            clock=lambda: NOW,
        )
        report = await worker.run_once()

        assert report.students == 1
        assert ("old", "faded") in graph.invalidated

    asyncio.run(_run())


def test_consolidation_worker_does_nothing_on_empty_memory():
    async def _run() -> None:
        graph = FakeGraph([])
        worker = MemoryConsolidationWorker(graph=graph, clock=lambda: NOW)
        report = await worker.run_once()

        assert report.students == 1
        assert graph.invalidated == []
        assert isinstance(await worker._consolidate_student("u1"), ConsolidationPlan)

    asyncio.run(_run())
