"""Очередь эпизодов и адаптер графа поверх Graphiti."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from agent_service.app.application.graph_memory.episodes import chat_episode, review_episode
from agent_service.app.application.graph_memory.facts import (
    EpisodeKind,
    FactOperation,
    FactTarget,
    GraphFact,
    MemoryEpisode,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import (
    EXHIBITS,
    STRUGGLES_WITH,
    group_id_for,
    node_uuid,
)
from agent_service.app.application.graph_memory.recipes import ReadIntent, Reranker, recipe_for
from agent_service.app.application.dto import CriterionResult, Review, TaskTestsResult
from agent_service.app.infrastructure.graph_memory.mongo_episode_queue import (
    DEAD,
    DONE,
    PENDING,
    MongoMemoryEpisodeQueue,
)


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

graphiti = pytest.importorskip("graphiti_core", reason="graphiti-core не установлен")


# --- очередь ---


class FakeCollection:
    """Минимальная коллекция Mongo: ровно те операции, что нужны очереди."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def update_one(self, query, update, upsert: bool = False):
        found = self._find(query)
        if found is not None:
            for key, value in (update.get("$set") or {}).items():
                found[key] = value
            return type("Res", (), {"upserted_id": None})()
        if not upsert:
            return type("Res", (), {"upserted_id": None})()
        doc = dict(update.get("$setOnInsert") or {})
        doc.update(update.get("$set") or {})
        doc.setdefault("episode_id", query.get("episode_id"))
        self.docs.append(doc)
        return type("Res", (), {"upserted_id": doc["episode_id"]})()

    async def find_one(self, query):
        return self._find(query)

    async def find_one_and_update(self, query, update, sort=None, return_document=None):
        for doc in sorted(self.docs, key=lambda item: item.get("created_at") or NOW):
            if not self._matches(doc, query):
                continue
            for key, value in (update.get("$set") or {}).items():
                doc[key] = value
            for key, value in (update.get("$inc") or {}).items():
                doc[key] = int(doc.get(key) or 0) + value
            return dict(doc)
        return None

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if self._matches(doc, query))

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]
        return type("Res", (), {"deleted_count": before - len(self.docs)})()

    async def create_index(self, *args, **kwargs):
        return None

    def _find(self, query):
        return next((doc for doc in self.docs if self._matches(doc, query)), None)

    def _matches(self, doc, query) -> bool:
        for key, want in query.items():
            value = doc.get(key)
            if isinstance(want, dict):
                if "$in" in want and value not in want["$in"]:
                    return False
                if "$lte" in want and not (value is not None and value <= want["$lte"]):
                    return False
                if "$lt" in want and not (value is not None and value < want["$lt"]):
                    return False
            elif value != want:
                return False
        return True


def _episode(episode_id: str = "ep1") -> MemoryEpisode:
    return MemoryEpisode(
        episode_id=episode_id,
        kind=EpisodeKind.REVIEW,
        user_id="u1",
        occurred_at=NOW,
        body="body",
        task_id="t1",
        submission_id="s1",
    )


def test_queue_is_idempotent():
    async def _run() -> None:
        queue = MongoMemoryEpisodeQueue(FakeCollection(), clock=lambda: NOW)
        assert await queue.enqueue(_episode()) is True
        # Повторная доставка того же события не удваивает работу.
        assert await queue.enqueue(_episode()) is False
        assert await queue.pending_count() == 1

    asyncio.run(_run())


def test_queue_refuses_episodes_without_an_owner():
    async def _run() -> None:
        queue = MongoMemoryEpisodeQueue(FakeCollection(), clock=lambda: NOW)
        anonymous = MemoryEpisode(
            episode_id="ep2",
            kind=EpisodeKind.CHAT,
            user_id="",
            occurred_at=NOW,
            body="",
        )
        assert await queue.enqueue(anonymous) is False

    asyncio.run(_run())


def test_claim_hides_the_episode_until_the_lease_expires():
    async def _run() -> None:
        collection = FakeCollection()
        queue = MongoMemoryEpisodeQueue(collection, lease_sec=300, clock=lambda: NOW)
        await queue.enqueue(_episode())

        taken = await queue.claim(limit=5, now=NOW)
        assert [item.episode_id for item in taken] == ["ep1"]
        # Второй рабочий тот же эпизод уже не получит.
        assert await queue.claim(limit=5, now=NOW) == []
        # Но после истечения аренды он вернётся в работу сам.
        again = await queue.claim(limit=5, now=NOW + timedelta(seconds=400))
        assert [item.episode_id for item in again] == ["ep1"]

    asyncio.run(_run())


def test_failed_episode_retries_then_dies():
    async def _run() -> None:
        collection = FakeCollection()
        clock = {"now": NOW}
        queue = MongoMemoryEpisodeQueue(
            collection,
            max_attempts=2,
            clock=lambda: clock["now"],
        )
        await queue.enqueue(_episode())

        await queue.claim(limit=1, now=NOW)
        await queue.mark_failed("ep1", "boom")
        assert collection.docs[0]["status"] == PENDING
        assert collection.docs[0]["visible_at"] > NOW

        clock["now"] = NOW + timedelta(hours=2)
        await queue.claim(limit=1, now=clock["now"])
        await queue.mark_failed("ep1", "boom again")
        assert collection.docs[0]["status"] == DEAD

    asyncio.run(_run())


def test_done_episodes_are_purged_but_dead_ones_stay():
    async def _run() -> None:
        collection = FakeCollection()
        queue = MongoMemoryEpisodeQueue(collection, keep_done_hours=1, clock=lambda: NOW)
        await queue.enqueue(_episode("ok"))
        await queue.enqueue(_episode("bad"))
        await queue.mark_done("ok")
        collection.docs[0]["finished_at"] = NOW - timedelta(days=5)
        collection.docs[1]["status"] = DEAD

        removed = await queue.purge_done()
        assert removed == 1
        assert [doc["status"] for doc in collection.docs] == [DEAD]
        assert DONE not in {doc["status"] for doc in collection.docs}

    asyncio.run(_run())


# --- сборка эпизодов ---


def test_review_episode_carries_the_facts_rules_can_read():
    review = Review(
        score=4,
        feedback="Ошибки проглатываются",
        suggestions=["Добавить обработку"],
        criteria=[CriterionResult(id="c1", text="Исключения обработаны", passed=False, note="голый except")],
        tests=TaskTestsResult(status="failed", total=5, passed=2, failed_names=["test_raises"]),
    )
    episode = review_episode("u1", review, task_id="t1", submission_id="s1")
    kinds = {item["kind"] for item in episode.observations}

    assert kinds == {"score", "criterion", "hidden_tests"}
    tests = next(item for item in episode.observations if item["kind"] == "hidden_tests")
    assert tests["status"] == "failed"
    assert tests["failed_names"] == ["test_raises"]
    assert episode.kind is EpisodeKind.REVIEW


def test_episode_id_is_stable_for_the_same_event():
    review = Review(score=7, feedback="ок")
    first = review_episode("u1", review, submission_id="s1")
    second = review_episode("u1", review, submission_id="s1")
    other = review_episode("u1", review, submission_id="s2")

    assert first.episode_id == second.episode_id
    assert first.episode_id != other.episode_id


def test_chat_episode_has_no_observations():
    episode = chat_episode("u1", "sess", "как быть?", "Эмма, QA", "вот так", turn_id="t")
    assert episode.observations == []
    assert episode.kind is EpisodeKind.CHAT
    assert "Student:" in episode.body


def test_episode_survives_a_round_trip_through_mongo():
    episode = _episode()
    restored = MemoryEpisode.from_document(episode.as_document())
    assert restored.episode_id == episode.episode_id
    assert restored.kind is episode.kind
    assert restored.occurred_at == episode.occurred_at


# --- адаптер ---


class FakeDriver:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []
        self.saved: list[Any] = []

    async def execute_query(self, query: str, **kwargs):
        self.queries.append((query, kwargs))
        return [{"group_id": "student_u1", "removed": 3}], None, None


class FakeGraphitiClient:
    def __init__(self) -> None:
        self.driver = FakeDriver()
        self.embedder = object()
        self.triplets: list[tuple[Any, Any, Any]] = []
        self.searches: list[dict[str, Any]] = []
        self.search_result: list[Any] = []
        self.schema_built = False

    async def build_indices_and_constraints(self) -> None:
        self.schema_built = True

    async def add_triplet(self, source_node, edge, target_node):
        self.triplets.append((source_node, edge, target_node))
        return type("Res", (), {"edges": [edge], "nodes": [source_node, target_node]})()

    async def search_(self, query, config, group_ids=None, center_node_uuid=None, search_filter=None, **kwargs):
        self.searches.append(
            {
                "query": query,
                "config": config,
                "group_ids": group_ids,
                "center": center_node_uuid,
                "filter": search_filter,
            }
        )
        return type("Res", (), {"edges": list(self.search_result)})()


def _adapter(client: FakeGraphitiClient):
    from agent_service.app.infrastructure.graph_memory.graphiti_graph_memory import (
        GraphitiGraphMemory,
    )

    return GraphitiGraphMemory(client=client, timeout_sec=5.0, write_timeout_sec=5.0)


def _fact(relation: str = STRUGGLES_WITH) -> GraphFact:
    return GraphFact(
        user_id="u1",
        relation=relation,
        target=FactTarget("skill", "error_handling", "Error handling"),
        statement="The student keeps failing error handling.",
        source=SourceKind.HIDDEN_TESTS,
        confidence=0.9,
        occurred_at=NOW,
        task_id="t1",
        submission_id="s1",
    )


def test_write_builds_our_own_triplet_with_provenance():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        result = await adapter.write(_fact())

        assert result.operation is FactOperation.ADD
        source_node, edge, target_node = client.triplets[0]
        group = group_id_for("u1")

        # Узлы наши и детерминированные: один навык — один узел на студента.
        assert target_node.uuid == node_uuid(group, "Skill", "error_handling")
        assert source_node.group_id == group
        assert edge.name == STRUGGLES_WITH
        # Время события, а не записи.
        assert edge.valid_at == NOW
        assert edge.attributes["source_kind"] == "hidden_tests"
        assert edge.attributes["submission_id"] == "s1"
        assert edge.attributes["occurrences"] == 1

    asyncio.run(_run())


def test_error_pattern_is_anchored_to_its_skill():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        fact = GraphFact(
            user_id="u1",
            relation=EXHIBITS,
            target=FactTarget("error_pattern", "bare_except", "bare except"),
            statement="The student uses a bare except.",
            source=SourceKind.REVIEW,
            occurred_at=NOW,
        )
        await adapter.write(fact)

        names = [edge.name for _, edge, _ in client.triplets]
        # Без связи с навыком ошибка не находилась бы поиском по близости.
        assert names == [EXHIBITS, "INSTANCE_OF"]

    asyncio.run(_run())


def test_read_filters_to_the_students_group_and_valid_window():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        await adapter.facts_for("u1", ReadIntent.STUDENT_NOW, query="как дела")

        call = client.searches[0]
        assert call["group_ids"] == ["student_u1"]
        # Закрытые окна в обычной выдаче не участвуют.
        assert call["filter"].invalid_at is not None
        assert set(call["filter"].edge_types) == set(recipe_for(ReadIntent.STUDENT_NOW).relations)

    asyncio.run(_run())


def test_task_context_centres_the_search_on_the_skill():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        await adapter.facts_for(
            "u1",
            ReadIntent.TASK_CONTEXT,
            query="обработка ошибок",
            skill_ids=["error_handling"],
        )
        call = client.searches[0]
        assert call["center"] == node_uuid(group_id_for("u1"), "Skill", "error_handling")

    asyncio.run(_run())


def test_node_distance_falls_back_to_rrf_without_an_anchor():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        await adapter.facts_for("u1", ReadIntent.TASK_CONTEXT, query="без навыка")
        # Ранжировать по близости не к чему — центра нет.
        assert client.searches[0]["center"] is None
        assert recipe_for(ReadIntent.TASK_CONTEXT).reranker is Reranker.NODE_DISTANCE

    asyncio.run(_run())


def test_history_recipe_keeps_closed_windows():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        await adapter.facts_for("u1", ReadIntent.SKILL_HISTORY, skill_ids=["testing"])
        assert client.searches[0]["filter"].invalid_at is None

    asyncio.run(_run())


def test_edges_map_back_to_domain_facts():
    from agent_service.app.infrastructure.graph_memory.graphiti_graph_memory import (
        _as_stored_fact,
    )

    class Edge:
        uuid = "e1"
        group_id = "student_u1"
        name = STRUGGLES_WITH
        fact = "The student keeps failing error handling."
        created_at = NOW
        valid_at = NOW - timedelta(days=2)
        invalid_at = None
        attributes = {
            "target_kind": "skill",
            "target_key": "error_handling",
            "target_name": "Error handling",
            "source_kind": "hidden_tests",
            "confidence": 0.9,
            "occurrences": 3,
            "last_seen_at": (NOW - timedelta(days=1)).isoformat(),
            "task_id": "t1",
        }

    stored = _as_stored_fact(Edge())
    assert isinstance(stored, StoredFact)
    assert stored.user_id == "u1"
    assert stored.source is SourceKind.HIDDEN_TESTS
    assert stored.occurrences == 3
    assert stored.is_valid


def test_service_edges_are_not_returned_as_facts():
    from agent_service.app.infrastructure.graph_memory.graphiti_graph_memory import (
        _as_stored_fact,
    )

    class Anchor:
        uuid = "e2"
        group_id = "student_u1"
        name = "INSTANCE_OF"
        fact = "The mistake belongs to error handling."
        created_at = NOW
        valid_at = NOW
        invalid_at = None
        attributes = {"target_kind": "skill", "target_key": "error_handling"}

    class Foreign:
        uuid = "e3"
        group_id = "student_u1"
        name = "SOMETHING_ELSE"
        fact = "not ours"
        created_at = NOW
        valid_at = NOW
        invalid_at = None
        attributes = {}

    assert _as_stored_fact(Anchor()) is None
    assert _as_stored_fact(Foreign()) is None


def test_forget_student_deletes_the_whole_subgraph():
    async def _run() -> None:
        client = FakeGraphitiClient()
        adapter = _adapter(client)
        removed = await adapter.forget_student("u1")

        query, params = client.driver.queries[0]
        assert "DETACH DELETE" in query
        assert params["group"] == "student_u1"
        assert removed == 3

    asyncio.run(_run())


def test_adapter_never_raises_when_the_graph_is_down():
    async def _run() -> None:
        class BrokenClient(FakeGraphitiClient):
            async def add_triplet(self, *args, **kwargs):
                raise RuntimeError("neo4j is down")

            async def search_(self, *args, **kwargs):
                raise RuntimeError("neo4j is down")

        adapter = _adapter(BrokenClient())
        assert (await adapter.write(_fact())).operation is FactOperation.SKIP
        assert await adapter.facts_for("u1", ReadIntent.STUDENT_NOW) == []

    asyncio.run(_run())


def test_disabled_adapter_is_inert():
    async def _run() -> None:
        from agent_service.app.infrastructure.graph_memory import NullGraphMemory

        adapter = NullGraphMemory()
        assert adapter.enabled is False
        assert (await adapter.write(_fact())).operation is FactOperation.SKIP
        assert await adapter.all_facts("u1") == []
        assert await adapter.forget_student("u1") == 0

    asyncio.run(_run())
