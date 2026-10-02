import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent_service.app.application.dto.student_profile import StudentProfile
from agent_service.app.application.memory.layers import VECTOR_LAYERS, layers_for_types
from agent_service.app.application.tools.past_reviews import (
    compress_student_facts,
    load_student_notes,
    save_review_memory,
)
from agent_service.app.application.tools.toolkit import ReviewToolkit
from agent_service.app.infrastructure.memory.layered_memory import LayeredMemory
from agent_service.app.infrastructure.student_profile import MongoStudentProfileRepository


class _Collection:
    """Минимальная замена motor-коллекции: find_one + update_one(upsert)."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.finds = 0

    async def find_one(self, query: dict) -> dict | None:
        self.finds += 1
        doc = self.docs.get(query["user_id"])
        return dict(doc) if doc is not None else None

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        key = query["user_id"]
        doc = self.docs.get(key)
        if doc is None:
            if not upsert:
                return
            doc = dict(update.get("$setOnInsert", {}))
        doc.update(update.get("$set", {}))
        for field, delta in update.get("$inc", {}).items():
            doc[field] = int(doc.get(field, 0)) + delta
        self.docs[key] = doc


class _Memory:
    def __init__(self) -> None:
        self.saved: list[tuple[str, dict]] = []

    async def retrieve(self, query, k=4, types=None):
        raise AssertionError("профиль студента не должен идти через векторный поиск")

    async def save_document(self, text: str, metadata: dict) -> None:
        self.saved.append((text, metadata))


def _repo() -> tuple[MongoStudentProfileRepository, _Collection]:
    coll = _Collection()
    return MongoStudentProfileRepository(coll), coll


def test_repository_keeps_one_record_per_student_and_overwrites_facts():
    async def _run() -> None:
        repo, coll = _repo()
        await repo.save("7", ["глотает ошибки голым except"], task_id="t1")
        await repo.save("7", ["слабая валидация входа", "ломает синтаксис"], task_id="t2")
        await repo.save("8", ["слабые или падающие тесты"])

        assert len(coll.docs) == 2
        profile = await repo.get("7")
        assert profile is not None
        assert profile.facts == ["слабая валидация входа", "ломает синтаксис"]
        assert profile.last_task_id == "t2"
        assert profile.reviews_count == 2
        assert profile.updated_at is not None and profile.updated_at.tzinfo is not None
        assert coll.docs["7"]["created_at"] <= coll.docs["7"]["updated_at"]

    asyncio.run(_run())


def test_repository_ignores_empty_input_and_unknown_students():
    async def _run() -> None:
        repo, coll = _repo()
        await repo.save("", ["факт"])
        await repo.save("7", [])
        await repo.save("7", ["  ", ""])
        assert coll.docs == {}
        assert await repo.get("") is None
        assert await repo.get("404") is None

    asyncio.run(_run())


def test_repository_makes_naive_mongo_datetimes_utc():
    async def _run() -> None:
        repo, coll = _repo()
        coll.docs["7"] = {
            "user_id": "7",
            "facts": ["a"],
            "updated_at": datetime(2026, 9, 1, 12, 0),
            "reviews_count": 3,
        }
        profile = await repo.get("7")
        assert profile is not None
        assert profile.updated_at == datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    asyncio.run(_run())


def test_save_review_memory_writes_profile_to_repository_not_to_vector_memory():
    async def _run() -> None:
        memory = _Memory()
        repo, coll = _repo()
        await save_review_memory(
            memory,
            task_id="t1",
            submission_id="s1",
            score=4,
            feedback="Валидации нет, тесты падают.",
            suggestions=["Ловить конкретное исключение"],
            user_id="7",
            profiles=repo,
        )
        types = [meta["type"] for _, meta in memory.saved]
        assert types == ["past_review"]
        profile = await repo.get("7")
        assert profile is not None
        assert profile.facts == ["слабые или падающие тесты", "слабая валидация входа"]
        assert profile.last_task_id == "t1"

    asyncio.run(_run())


def test_second_review_merges_previous_facts_up_to_two():
    async def _run() -> None:
        memory = _Memory()
        repo, _ = _repo()
        await repo.save("7", ["слабая валидация входа", "ломает синтаксис"])
        await save_review_memory(
            memory,
            task_id="t2",
            submission_id="s2",
            score=5,
            feedback="Тесты падают.",
            suggestions=[],
            user_id="7",
            profiles=repo,
        )
        profile = await repo.get("7")
        assert profile is not None
        assert profile.facts == ["слабые или падающие тесты", "слабая валидация входа"]
        assert profile.reviews_count == 2

    asyncio.run(_run())


def test_no_user_or_no_repository_writes_no_profile():
    async def _run() -> None:
        memory = _Memory()
        repo, coll = _repo()
        await save_review_memory(
            memory, "t1", "s1", 3, "Голый except.", [], user_id=None, profiles=repo,
        )
        await save_review_memory(
            memory, "t1", "s1", 3, "Голый except.", [], user_id="7", profiles=None,
        )
        assert coll.docs == {}
        assert [meta["type"] for _, meta in memory.saved] == ["past_review"]

    asyncio.run(_run())


def test_high_score_without_findings_does_not_create_profile():
    async def _run() -> None:
        repo, coll = _repo()
        await save_review_memory(
            _Memory(), "t1", "s1", 10, "Всё хорошо.", [], user_id="7", profiles=repo,
        )
        assert coll.docs == {}

    asyncio.run(_run())


def test_solution_dump_in_suggestion_is_not_stored_as_fact():
    async def _run() -> None:
        repo, coll = _repo()
        dump = "def a(): return 1 def b(): return 2 def c(): return 3"
        await save_review_memory(
            _Memory(), "t1", "s1", 6, "Ок.", [dump], user_id="7", profiles=repo,
        )
        assert coll.docs == {}

    asyncio.run(_run())


def test_load_student_notes_reads_by_key_and_scopes_to_user():
    async def _run() -> None:
        repo, coll = _repo()
        await repo.save("7", ["слабая валидация входа", "ломает синтаксис"], task_id="t3")
        await repo.save("8", ["чужой профиль"])

        assert await load_student_notes(repo, user_id=None) == []
        assert await load_student_notes(None, user_id="7") == []
        assert await load_student_notes(repo, user_id="404") == []

        hits = await load_student_notes(repo, user_id="7")
        assert len(hits) == 1
        message = hits[0].message
        assert "Профиль студента" in message
        assert "слабая валидация входа; ломает синтаксис" in message
        assert "user=7" in message and "task=t3" in message
        assert "чужой профиль" not in message
        # find_one только на реальные обращения (без user_id и без репозитория — ни одного)
        assert coll.finds == 2

    asyncio.run(_run())


def test_stale_profile_is_ignored_and_not_merged():
    async def _run() -> None:
        repo, coll = _repo()
        await repo.save("7", ["ломает синтаксис"])
        coll.docs["7"]["updated_at"] = datetime.now(tz=timezone.utc) - timedelta(days=200)

        assert await load_student_notes(repo, user_id="7") == []

        await save_review_memory(
            _Memory(), "t2", "s2", 5, "Тесты падают.", [], user_id="7", profiles=repo,
        )
        profile = await repo.get("7")
        assert profile is not None
        assert profile.facts == ["слабые или падающие тесты"]

    asyncio.run(_run())


def test_toolkit_puts_profile_into_report_findings():
    async def _run() -> None:
        repo, _ = _repo()
        await repo.save("7", ["не думает про крайние случаи"])
        toolkit = ReviewToolkit(_Memory_no_past(), profiles=repo)
        with patch(
            "agent_service.app.application.tools.toolkit.compile_python",
            new=AsyncMock(return_value=None),
        ), patch(
            "agent_service.app.application.tools.toolkit.run_python_tests",
            new=AsyncMock(return_value=(None, None)),
        ):
            report = await toolkit.inspect("x = 1\n", "задача", user_id="7")
        messages = [item.message for item in report.findings]
        assert any(
            "Профиль студента" in text and "не думает про крайние случаи" in text
            for text in messages
        )

    asyncio.run(_run())


class _Memory_no_past:
    async def retrieve(self, query, k=4, types=None):
        return []

    async def save_document(self, text: str, metadata: dict) -> None:
        return None


def test_compress_student_facts_returns_list_capped_at_two():
    facts = compress_student_facts(
        score=3,
        feedback="Голый except, нет валидации, тесты падают",
        suggestions=[],
        previous=["ломает синтаксис"],
    )
    assert isinstance(facts, list)
    assert facts == ["глотает ошибки голым except", "слабые или падающие тесты"] or len(facts) == 2
    assert compress_student_facts(score=9, feedback="ок", suggestions=[], previous=None) == []


def test_student_notes_no_longer_have_a_vector_layer():
    assert "student" not in VECTOR_LAYERS
    assert layers_for_types(None) == list(VECTOR_LAYERS)


def test_layered_memory_refuses_student_notes_and_never_searches_without_types():
    async def _run() -> None:
        added: list = []

        class _Store:
            async def add_documents(self, documents, metadatas, ids):
                added.append(ids)

            async def similarity_search(self, **kwargs):
                raise AssertionError("поиск без допустимых типов не должен доходить до Chroma")

        memory = LayeredMemory(
            stores={"semantic": _Store(), "episodic": _Store()},
            embeddings=SimpleNamespace(),
            chat_history_repository=SimpleNamespace(),
        )
        await memory.save_document(
            "Студент 7. Типичное: ломает синтаксис.",
            {"type": "student_note", "user_id": "7", "id": "student_7"},
        )
        assert added == []

        found = await memory._search_layer(
            layer="semantic", query="q", k=3, types=set(), query_embedding=[0.0],
        )
        assert found == []

    asyncio.run(_run())


def test_profile_dataclass_defaults():
    profile = StudentProfile(user_id="7")
    assert profile.facts == [] and profile.reviews_count == 0 and profile.updated_at is None
