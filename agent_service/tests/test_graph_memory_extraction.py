"""Извлечение фактов: правила без модели и разбор ответа модели."""

import json
from datetime import datetime, timedelta, timezone

from agent_service.app.application.graph_memory.extraction import (
    fixed_pattern_facts,
    observations_to_facts,
    parse_extraction,
    pattern_skill,
)
from agent_service.app.application.graph_memory.facts import (
    EpisodeKind,
    FactOperation,
    FactTarget,
    MemoryEpisode,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    PREFERS,
    STRUGGLES_WITH,
    WORKED_ON,
)


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _episode(observations, kind=EpisodeKind.REVIEW, body="") -> MemoryEpisode:
    return MemoryEpisode(
        episode_id="ep1",
        kind=kind,
        user_id="u1",
        occurred_at=NOW,
        body=body,
        task_id="t1",
        submission_id="s1",
        task_title="Orders API",
        observations=observations,
    )


def test_failed_criterion_becomes_a_gap():
    episode = _episode(
        [
            {"kind": "criterion", "passed": False, "text": "Исключения не проглатываются", "note": "голый except"},
            {"kind": "criterion", "passed": True, "text": "Есть тесты на основной сценарий"},
        ]
    )
    facts = observations_to_facts(episode)
    by_relation = {(fact.relation, fact.target.key): fact for fact in facts}

    assert (STRUGGLES_WITH, "error_handling") in by_relation
    assert (DEMONSTRATES, "testing") in by_relation
    assert (WORKED_ON, "t1") in by_relation
    # Без прогона тестов положительное свидетельство — только мнение модели.
    assert by_relation[(DEMONSTRATES, "testing")].source is SourceKind.REVIEW


def test_green_tests_promote_positive_evidence():
    episode = _episode(
        [
            {"kind": "criterion", "passed": True, "text": "Валидация входа на месте"},
            {"kind": "hidden_tests", "status": "passed", "total": 6, "passed": 6, "failed_names": []},
        ]
    )
    facts = {fact.target.key: fact for fact in observations_to_facts(episode) if fact.relation == DEMONSTRATES}

    assert facts["validation"].source is SourceKind.HIDDEN_TESTS
    assert facts["validation"].confidence > 0.7


def test_red_tests_outweigh_passed_criteria():
    episode = _episode(
        [
            {"kind": "criterion", "passed": True, "text": "Обработка ошибок"},
            {
                "kind": "hidden_tests",
                "status": "failed",
                "total": 6,
                "passed": 2,
                "failed_names": ["test_error_handling_on_empty"],
            },
        ]
    )
    facts = observations_to_facts(episode)
    positives = [fact for fact in facts if fact.relation == DEMONSTRATES]
    gaps = [fact for fact in facts if fact.relation == STRUGGLES_WITH]

    # Код запускали, и он упал: засчитывать «критерий пройден» нельзя.
    assert positives == []
    assert gaps and gaps[0].source is SourceKind.HIDDEN_TESTS
    assert "hidden tests failed" in gaps[0].statement


def test_same_skill_failing_and_passing_counts_as_failing():
    episode = _episode(
        [
            {"kind": "criterion", "passed": False, "text": "Тесты ничего не проверяют"},
            {"kind": "criterion", "passed": True, "text": "Есть тесты"},
        ]
    )
    relations = {(fact.relation, fact.target.key) for fact in observations_to_facts(episode)}
    assert (STRUGGLES_WITH, "testing") in relations
    assert (DEMONSTRATES, "testing") not in relations


def test_fixed_pattern_needs_green_tests_and_clean_criteria():
    stored = StoredFact(
        edge_uuid="e1",
        user_id="u1",
        relation=EXHIBITS,
        target=FactTarget("error_pattern", "bare_except", "bare except"),
        statement="The student catches everything with a bare except.",
        source=SourceKind.REVIEW,
        confidence=0.8,
        occurred_at=NOW - timedelta(days=5),
        created_at=NOW - timedelta(days=5),
    )

    green = _episode(
        [
            {"kind": "criterion", "passed": True, "text": "Исключения обработаны"},
            {"kind": "hidden_tests", "status": "passed", "total": 4, "passed": 4},
        ]
    )
    closed = fixed_pattern_facts(green, [stored])
    assert len(closed) == 1
    assert closed[0].operation is FactOperation.INVALIDATE
    # Закрытие — от прогона кода, а не от суждения модели.
    assert closed[0].source is SourceKind.HIDDEN_TESTS

    still_failing = _episode(
        [
            {"kind": "criterion", "passed": False, "text": "Исключения обработаны"},
            {"kind": "hidden_tests", "status": "passed", "total": 4, "passed": 4},
        ]
    )
    assert fixed_pattern_facts(still_failing, [stored]) == []

    no_tests = _episode([{"kind": "criterion", "passed": True, "text": "Исключения обработаны"}])
    assert fixed_pattern_facts(no_tests, [stored]) == []


def test_parse_extraction_keeps_only_valid_facts():
    episode = _episode([], kind=EpisodeKind.CHAT, body="chat")
    raw = json.dumps(
        [
            {
                "relation": "EXHIBITS",
                "target_kind": "error_pattern",
                "target_key": "Bare Except",
                "statement": "The student keeps catching every exception with a bare except.",
                "confidence": 0.8,
            },
            {
                "relation": "STRUGGLES_WITH",
                "target_kind": "skill",
                "target_key": "made_up_skill",
                "statement": "The student struggles with an invented skill.",
            },
            {
                "relation": "WORKED_ON",
                "target_kind": "task",
                "target_key": "t1",
                "statement": "The student worked on the task.",
            },
            {
                "relation": "PREFERS",
                "target_kind": "preference",
                "target_key": "short_examples",
                "statement": "Студент просит короткие примеры.",
            },
            {
                "relation": "PREFERS",
                "target_kind": "preference",
                "target_key": "step_by_step",
                "statement": "The student asks for step by step explanations.",
                "status": "resolved",
            },
        ]
    )
    facts = parse_extraction(raw, episode)
    keys = {(fact.relation, fact.target.key) for fact in facts}

    assert (EXHIBITS, "bare_except") in keys
    # Навык вне таксономии отброшен.
    assert not any(fact.target.key == "made_up_skill" for fact in facts)
    # WORKED_ON выводится кодом, модели его предлагать нельзя.
    assert not any(fact.relation == WORKED_ON for fact in facts)
    # Факт не на английском не попадает в граф.
    assert (PREFERS, "short_examples") not in keys

    resolved = next(fact for fact in facts if fact.target.key == "step_by_step")
    assert resolved.operation is FactOperation.INVALIDATE
    assert resolved.source is SourceKind.CHAT


def test_parse_extraction_survives_fences_and_garbage():
    episode = _episode([])
    fenced = (
        "Here you go:\n```json\n"
        '[{"relation": "EXHIBITS", "target_kind": "error_pattern", "target_key": "mutable_default",'
        ' "statement": "The student uses a mutable default argument again.", "confidence": 2}]'
        "\n```\n"
    )
    facts = parse_extraction(fenced, episode)
    assert len(facts) == 1
    # Уверенность за пределами диапазона прижимается.
    assert facts[0].confidence == 1.0

    assert parse_extraction("no json at all", episode) == []
    assert parse_extraction("", episode) == []


def test_pattern_skill_falls_back_to_classifier():
    assert pattern_skill(FactTarget("error_pattern", "bare_except")) == "error_handling"
    assert pattern_skill(FactTarget("error_pattern", "unseen_test_gap", "missing test")) == "testing"
    assert pattern_skill(FactTarget("skill", "testing")) is None
