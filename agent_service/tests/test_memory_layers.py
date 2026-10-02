import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from agent_service.app.application.decisions.questions import Answers, parse_answers
from agent_service.app.application.decisions.policies import rerank_questions
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.memory.layers import scope_filter
from agent_service.app.application.memory.provenance import (
    merged_metadata,
    reinforced_metadata,
    usefulness_multiplier,
)
from agent_service.app.infrastructure.memory.layered_memory import LayeredMemory
from agent_service.app.infrastructure.memory.vector_store import (
    VectorStoreSearchResult,
    chroma_where,
)


class _Store:
    """Двойник векторного хранилища с поддержкой where-фильтра Chroma."""

    def __init__(self, distance: float = 0.5) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.searches: list[dict[str, Any]] = []
        self.distance = distance

    async def add_documents(self, documents, metadatas, ids):
        for text, meta, doc_id in zip(documents, metadatas, ids):
            self.docs[doc_id] = {"text": text, "meta": dict(meta)}
        return list(ids)

    async def update_metadata(self, ids, metadatas):
        updated = 0
        for doc_id, meta in zip(ids, metadatas):
            if doc_id in self.docs:
                self.docs[doc_id]["meta"] = dict(meta)
                updated += 1
        return updated

    async def similarity_search(self, query, k=5, where=None, query_embedding=None):
        self.searches.append({"query": query, "k": k, "where": where})
        hits = [
            (doc_id, item)
            for doc_id, item in self.docs.items()
            if _matches(item["meta"], where)
        ][:k]
        return VectorStoreSearchResult(
            documents=[item["text"] for _, item in hits],
            metadatas=[dict(item["meta"]) for _, item in hits],
            ids=[doc_id for doc_id, _ in hits],
            scores=[self.distance for _ in hits],
        )


def _matches(meta: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_matches(meta, clause) for clause in where["$and"])
    if "$or" in where:
        return any(_matches(meta, clause) for clause in where["$or"])
    return all(str(meta.get(key)) == str(value) for key, value in where.items())


class _Decisions:
    def __init__(self, answers: Answers | None = None, enabled: bool = True) -> None:
        self._answers = answers if answers is not None else Answers.unavailable("none")
        self._enabled = enabled
        self.calls: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def ask(self, state, questions, label: str = "") -> Answers:
        self.calls.append(label)
        return self._answers


class _Embeddings:
    name = "fake"

    async def embed_query(self, text: str) -> list[float]:
        return [0.0, 1.0]

    async def embed_documents(self, texts):
        return [[0.0, 1.0] for _ in texts]


def _memory(stores: dict[str, _Store] | None = None, **kwargs) -> LayeredMemory:
    stores = stores or {"semantic": _Store(), "episodic": _Store()}
    return LayeredMemory(
        stores=stores,
        embeddings=_Embeddings(),
        chat_history_repository=SimpleNamespace(),
        **kwargs,
    )


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_chroma_where_combines_types_and_owner():
    assert chroma_where(None, None) is None
    assert chroma_where({"bugs"}, None) == {"type": "bugs"}
    assert chroma_where({"past_review"}, {"user_id": "7"}) == {
        "$and": [{"type": "past_review"}, {"user_id": "7"}]
    }
    combined = chroma_where({"past_review", "chat_episode"}, {"user_id": "7"})
    assert combined["$and"][0]["$or"] == [{"type": "chat_episode"}, {"type": "past_review"}]


def test_owner_filter_applies_only_to_private_types():
    scope = {"user_id": "7", "session_id": "s1"}
    # общее знание владельца не имеет — фильтр по нему отрезал бы всю выдачу
    assert scope_filter({"best_practice"}, scope) == {}
    assert scope_filter({"best_practice", "chat_episode"}, scope) == {}
    assert scope_filter({"past_review"}, scope) == {"user_id": "7"}
    assert scope_filter({"chat_episode"}, scope) == {"user_id": "7", "session_id": "s1"}
    assert scope_filter({"chat_episode"}, None) == {}


def test_private_layer_is_filtered_in_the_store_not_after_top_k():
    async def _run() -> None:
        episodic = _Store()
        semantic = _Store()
        memory = _memory({"semantic": semantic, "episodic": episodic})
        for index in range(3):
            await episodic.add_documents(
                [f"чужое ревью {index}"],
                [{"type": "past_review", "user_id": "99", "saved_at": _now()}],
                [f"other_{index}"],
            )
        await episodic.add_documents(
            ["моё ревью"],
            [{"type": "past_review", "user_id": "7", "saved_at": _now()}],
            ["mine"],
        )

        found = await memory.retrieve(
            query="пустой список",
            k=2,
            types={"past_review"},
            scope={"user_id": "7"},
        )
        assert [doc.text for doc in found] == ["моё ревью"]
        assert episodic.searches[-1]["where"] == {
            "$and": [{"type": "past_review"}, {"user_id": "7"}]
        }
        # семантический слой в этот запрос не ходит: там нет таких типов
        assert semantic.searches == []

    asyncio.run(_run())


def test_search_puts_store_id_into_metadata_for_later_reinforcement():
    async def _run() -> None:
        store = _Store()
        memory = _memory({"semantic": store, "episodic": _Store()})
        await store.add_documents(
            ["практика"], [{"type": "best_practice", "saved_at": _now()}], ["bp_1"]
        )
        found = await memory.retrieve(query="практика", k=1, types={"best_practice"})
        assert found[0].metadata["id"] == "bp_1"
        assert found[0].metadata["layer"] == "semantic"

    asyncio.run(_run())


def test_repeat_merges_into_existing_document_instead_of_piling_duplicates():
    async def _run() -> None:
        store = _Store(distance=0.02)
        memory = _memory({"semantic": _Store(), "episodic": store}, dedup_similarity=0.9)
        meta = {
            "type": "chat_episode",
            "session_id": "s1",
            "user_id": "7",
            "id": "episode_first",
        }
        await memory.save_document("Пользователь: падает на пустом списке. Эмма: проверь длину.", meta)
        await memory.save_document(
            "Пользователь: снова падает на пустом списке. Эмма: проверь длину.",
            {**meta, "id": "episode_second"},
        )

        assert list(store.docs) == ["episode_first"]
        kept = store.docs["episode_first"]
        assert "снова" in kept["text"]
        assert kept["meta"]["merges"] == 1
        assert kept["meta"]["created_at"] <= kept["meta"]["saved_at"]

    asyncio.run(_run())


def test_distant_episode_is_saved_as_a_new_document():
    async def _run() -> None:
        store = _Store(distance=0.5)
        memory = _memory({"semantic": _Store(), "episodic": store}, dedup_similarity=0.9)
        base = {"type": "chat_episode", "session_id": "s1", "user_id": "7"}
        await memory.save_document("Пользователь: падает на пустом списке.", {**base, "id": "a"})
        await memory.save_document("Пользователь: как назвать модуль?", {**base, "id": "b"})
        assert set(store.docs) == {"a", "b"}

    asyncio.run(_run())


def test_reinforce_counts_uses_and_raises_the_weight():
    async def _run() -> None:
        store = _Store()
        memory = _memory({"semantic": store, "episodic": _Store()})
        await store.add_documents(
            ["практика"], [{"type": "best_practice", "saved_at": _now()}], ["bp_1"]
        )
        first = await memory.retrieve(query="практика", k=1, types={"best_practice"})
        assert await memory.reinforce(first) == 1
        # следующий ход читает уже обновлённые метаданные
        second = await memory.retrieve(query="практика", k=1, types={"best_practice"})
        assert second[0].metadata["uses"] == 1
        assert await memory.reinforce(second) == 1

        meta = store.docs["bp_1"]["meta"]
        assert meta["uses"] == 2 and meta["last_used_at"]
        assert usefulness_multiplier(meta) > usefulness_multiplier(
            {k: v for k, v in meta.items() if k != "uses"}
        )

    asyncio.run(_run())


def test_reinforce_is_skipped_without_ids_or_when_turned_off():
    async def _run() -> None:
        store = _Store()
        memory = _memory({"semantic": store, "episodic": _Store()})
        assert await memory.reinforce([RetrievedDocument(text="x", metadata={})]) == 0

        off = _memory({"semantic": store, "episodic": _Store()}, reinforce_enabled=False)
        doc = RetrievedDocument(text="x", metadata={"id": "bp_1", "layer": "semantic"})
        assert await off.reinforce([doc]) == 0

    asyncio.run(_run())


def test_usefulness_grows_with_uses_but_saturates():
    base = {"type": "best_practice", "saved_at": _now()}
    weights = [usefulness_multiplier({**base, "uses": uses}) for uses in range(4)]
    assert weights == sorted(weights)
    # каждое следующее попадание добавляет меньше предыдущего
    steps = [later - earlier for earlier, later in zip(weights, weights[1:])]
    assert steps == sorted(steps, reverse=True)
    # и прибавка ограничена сверху, сколько бы раз документ ни использовали
    assert usefulness_multiplier({**base, "uses": 10_000}) - weights[0] < 0.36


def test_stale_document_loses_to_a_fresh_one_even_with_uses():
    now = datetime.now(tz=timezone.utc)
    stale = {
        "type": "chat_episode",
        "saved_at": (now - timedelta(days=20)).isoformat(),
        "uses": 3,
    }
    fresh = {"type": "chat_episode", "saved_at": now.isoformat()}
    assert usefulness_multiplier(fresh, now=now) > usefulness_multiplier(stale, now=now)


def test_write_gate_drops_a_low_value_episode():
    async def _run() -> None:
        store = _Store()
        answers = Answers(items={"keep": 0.2}, source="jev")
        decisions = _Decisions(answers)
        memory = _memory(
            {"semantic": _Store(), "episodic": store},
            decisions=decisions,
        )
        await memory.save_document(
            "Пользователь: привет. Джон: привет, что по задаче?",
            {"type": "chat_episode", "session_id": "s1", "user_id": "7", "id": "small_talk"},
        )
        assert store.docs == {}
        assert decisions.calls == ["memory_write_gate"]

    asyncio.run(_run())


def test_write_gate_keeps_the_record_when_the_model_is_silent():
    async def _run() -> None:
        store = _Store()
        memory = _memory(
            {"semantic": _Store(), "episodic": store},
            decisions=_Decisions(Answers.unavailable("transport_error")),
        )
        await memory.save_document(
            "Пользователь: падает на пустом списке. Эмма: проверь длину перед orders[0].",
            {"type": "chat_episode", "session_id": "s1", "user_id": "7", "id": "real"},
        )
        assert list(store.docs) == ["real"]

    asyncio.run(_run())


def test_write_gate_does_not_touch_shared_knowledge():
    async def _run() -> None:
        store = _Store()
        decisions = _Decisions(Answers(items={"keep": 0.0}, source="jev"))
        memory = _memory({"semantic": store, "episodic": _Store()}, decisions=decisions)
        await memory.save_document(
            "Валидируй вход на границе модуля, а не внутри обработчика.",
            {"type": "best_practice", "id": "bp_1"},
        )
        assert list(store.docs) == ["bp_1"]
        assert decisions.calls == []

    asyncio.run(_run())


def _rerank_answers(levels: dict[int, float], confidence: float = 0.9) -> Answers:
    questions = rerank_questions(len(levels))
    body = {
        "answers": {
            f"doc_{index}": {
                "type": "score",
                "score": score,
                "confidence": confidence,
                "probabilities": {},
            }
            for index, score in levels.items()
        }
    }
    return parse_answers(body, questions)


def test_rerank_drops_irrelevant_documents_and_reorders_the_rest():
    async def _run() -> None:
        store = _Store()
        memory = _memory(
            {"semantic": store, "episodic": _Store()},
            decisions=_Decisions(_rerank_answers({0: 0.0, 1: 2.0, 2: 1.0})),
        )
        for index, text in enumerate(["мимо", "точно в тему", "рядом"]):
            await store.add_documents(
                [text], [{"type": "best_practice", "saved_at": _now()}], [f"bp_{index}"]
            )

        found = await memory.retrieve(query="вопрос", k=3, types={"best_practice"})
        assert [doc.text for doc in found] == ["точно в тему", "рядом"]

    asyncio.run(_run())


def test_rerank_keeps_the_vector_order_when_the_model_is_unavailable():
    async def _run() -> None:
        store = _Store()
        memory = _memory(
            {"semantic": store, "episodic": _Store()},
            decisions=_Decisions(Answers.unavailable("cooldown")),
        )
        for index in range(3):
            await store.add_documents(
                [f"док {index}"], [{"type": "best_practice", "saved_at": _now()}], [f"bp_{index}"]
            )
        found = await memory.retrieve(query="вопрос", k=2, types={"best_practice"})
        assert [doc.text for doc in found] == ["док 0", "док 1"]

    asyncio.run(_run())


def test_rerank_is_skipped_when_the_model_is_not_confident():
    async def _run() -> None:
        store = _Store()
        memory = _memory(
            {"semantic": store, "episodic": _Store()},
            decisions=_Decisions(_rerank_answers({0: 0.0, 1: 2.0}, confidence=0.2)),
            min_confidence=0.6,
        )
        for index in range(2):
            await store.add_documents(
                [f"док {index}"], [{"type": "best_practice", "saved_at": _now()}], [f"bp_{index}"]
            )
        found = await memory.retrieve(query="вопрос", k=2, types={"best_practice"})
        assert [doc.text for doc in found] == ["док 0", "док 1"]

    asyncio.run(_run())


def test_merged_metadata_keeps_history_and_refreshes_freshness():
    old = {"created_at": "2026-01-01T00:00:00+00:00", "uses": 3, "merges": 1}
    fresh = {"type": "chat_episode", "saved_at": "2026-02-01T00:00:00+00:00"}
    merged = merged_metadata(old, fresh)
    assert merged["created_at"] == "2026-01-01T00:00:00+00:00"
    assert merged["uses"] == 3 and merged["merges"] == 2
    assert merged["saved_at"] > old["created_at"]


def test_reinforced_metadata_is_monotonic():
    meta = {"type": "bugs"}
    for expected in (1, 2, 3):
        meta = reinforced_metadata(meta)
        assert meta["uses"] == expected
