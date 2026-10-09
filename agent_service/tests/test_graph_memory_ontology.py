"""Онтология графа: якоря навыков, слаги ошибок, идентификаторы узлов."""

import pytest

from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    ERROR_PATTERN,
    EXHIBITS,
    PRACTISES,
    SKILL,
    SKILL_BY_ID,
    STUDENT,
    classify_skill,
    group_id_for,
    node_uuid,
    normalize_pattern_slug,
    normalize_skill_id,
    pattern_summary,
    relation_allowed,
    skill_of_pattern,
    user_id_of_group,
)


def test_taxonomy_matches_trajectory_ids():
    """Навыки графа — те же 14, что у модели знаний в submission_service."""
    assert len(SKILL_BY_ID) == 14
    assert "error_handling" in SKILL_BY_ID
    assert "async_concurrency" in SKILL_BY_ID
    # Имена английские: факты и узлы читаются одним языком.
    assert all(name.isascii() for name in (skill.name for skill in SKILL_BY_ID.values()))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("error_handling", "error_handling"),
        ("Error Handling", "error_handling"),
        ("exceptions", "error_handling"),
        ("db", "data_storage"),
        ("edge_case", "edge_cases"),
        ("algorithm", "algorithms"),
        ("", None),
        ("мимо", None),
        ("made_up_skill", None),
    ],
)
def test_skill_normalization(raw, expected):
    assert normalize_skill_id(raw) == expected


def test_classify_skill_reads_russian_and_english():
    assert classify_skill("Голый except проглатывает ошибку") == "error_handling"
    assert classify_skill("bare except swallows the failure") == "error_handling"
    assert classify_skill("нет проверки на пустой список") == "edge_cases"
    assert classify_skill("") is None


def test_pattern_slug_is_restricted():
    assert normalize_pattern_slug("Bare Except") == "bare_except"
    assert normalize_pattern_slug("n+1 query") == "n1_query"
    # Кириллица и слишком короткое отбрасываются: иначе граф обрастает мусором.
    assert normalize_pattern_slug("голый except") is None
    assert normalize_pattern_slug("ab") is None
    assert normalize_pattern_slug(None) is None


def test_known_patterns_are_anchored_to_skills():
    assert skill_of_pattern("bare_except") == "error_handling"
    assert skill_of_pattern("n_plus_one_query") == "data_storage"
    assert skill_of_pattern("unknown_slug") is None
    assert pattern_summary("unknown_slug") == "Unknown slug"


def test_relation_allowed_only_for_declared_pairs():
    assert relation_allowed(EXHIBITS, STUDENT, ERROR_PATTERN)
    assert relation_allowed(DEMONSTRATES, STUDENT, SKILL)
    # Студент не «тренирует» навык — это связь задачи.
    assert not relation_allowed(PRACTISES, STUDENT, SKILL)
    assert not relation_allowed("INVENTED", STUDENT, SKILL)


def test_group_id_isolates_students():
    assert group_id_for("42") == "student_42"
    # Дефис ломает полнотекстовый поиск, поэтому его не остаётся.
    assert "-" not in group_id_for("ab-cd")
    assert user_id_of_group(group_id_for("42")) == "42"
    with pytest.raises(ValueError):
        group_id_for("  ")


def test_node_uuid_is_deterministic_and_scoped():
    first = node_uuid("student_1", SKILL, "testing")
    again = node_uuid("student_1", SKILL, "testing")
    other_student = node_uuid("student_2", SKILL, "testing")
    other_skill = node_uuid("student_1", SKILL, "security")

    assert first == again
    # Разные студенты — разные узлы: изоляция по построению.
    assert first != other_student
    assert first != other_skill
