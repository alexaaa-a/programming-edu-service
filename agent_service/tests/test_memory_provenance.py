from datetime import datetime, timedelta, timezone

from agent_service.app.application.memory.provenance import (
    compress_memory_text,
    enrich_provenance,
    format_provenance,
    is_fresh,
    prepare_memory_write,
    recency_multiplier,
    validate_memory_text,
)


def test_enrich_provenance_sets_source_and_timestamps():
    meta = enrich_provenance({"type": "past_review", "task_id": 42}, text="hello")
    assert meta["source"] == "review_pipeline"
    assert meta["writer"]
    assert meta["saved_at"]
    assert meta["created_at"]
    assert meta["task_id"] == "42"
    assert meta["verified"] == 1


def test_prepare_write_rejects_llm_fluff():
    decision = prepare_memory_write(
        "Как языковая модель я не могу оценить этот код полностью.",
        {"type": "past_review", "submission_id": "1"},
    )
    assert decision.accept is False
    assert decision.reason == "llm_fluff"


def test_prepare_write_accepts_anchored_review():
    decision = prepare_memory_write(
        "Скор 4/10. Голый except. Правки: лови ValueError.",
        {
            "type": "past_review",
            "source": "review_pipeline",
            "writer": "review_orchestrator",
            "submission_id": "99",
            "task_id": "1001",
            "user_id": "7",
        },
    )
    assert decision.accept is True
    assert "Скор 4/10" in decision.text
    assert decision.metadata["source"] == "review_pipeline"


def test_prepare_write_rejects_student_note_without_user():
    decision = prepare_memory_write(
        "Студент X. Типичное: слабая валидация.",
        {"type": "student_note"},
    )
    assert decision.accept is False
    assert decision.reason == "student_note_without_user"


def test_prepare_write_rejects_past_review_without_user():
    decision = prepare_memory_write(
        "Скор 4/10. Нужно чинить except.",
        {"type": "past_review", "submission_id": "1"},
    )
    assert decision.accept is False
    assert decision.reason == "past_review_without_user"


def test_compress_strips_solution_dump_from_notes():
    text = (
        "Короткий совет. "
        "```python\n"
        + ("def f():\n    return 1\n" * 40)
        + "```"
    )
    compressed = compress_memory_text(text, doc_type="chat_episode")
    assert "код опущен" in compressed or "фрагмент опущен" in compressed
    assert "def f" not in compressed


def test_freshness_drops_old_episodic():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    old = (now - timedelta(days=60)).isoformat()
    assert is_fresh({"type": "past_review", "saved_at": old}, now=now) is False
    assert is_fresh({"type": "best_practice", "saved_at": old}, now=now) is True


def test_recency_prefers_newer_docs():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    fresh = recency_multiplier(
        {"type": "chat_episode", "saved_at": now.isoformat()},
        now=now,
    )
    stale = recency_multiplier(
        {"type": "chat_episode", "saved_at": (now - timedelta(days=14)).isoformat()},
        now=now,
    )
    assert fresh > stale


def test_format_provenance_includes_age_and_ids():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    text = format_provenance(
        {
            "type": "past_review",
            "source": "review_pipeline",
            "task_id": "1001",
            "user_id": "7",
            "saved_at": (now - timedelta(days=2)).isoformat(),
        },
        now=now,
    )
    assert "past_review" in text
    assert "source=review_pipeline" in text
    assert "task=1001" in text
    assert "user=7" in text
    assert "age=2d" in text


def test_validate_solution_dump():
    blob = "def a():\n  return 1\ndef b():\n  return 2\ndef c():\n  return 3\n" + ("x\n" * 5)
    ok, reason = validate_memory_text(
        blob,
        doc_type="past_review",
        metadata={"submission_id": "1", "user_id": "7"},
    )
    assert ok is False
    assert reason == "solution_dump"
