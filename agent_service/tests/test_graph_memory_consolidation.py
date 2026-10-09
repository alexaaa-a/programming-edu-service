"""Консолидация: забывание, обобщение, сверка с моделью знаний, дубли."""

from datetime import datetime, timedelta, timezone

from agent_service.app.application.graph_memory.consolidation import (
    CHRONIC_OCCURRENCES,
    FORGET_FLOOR,
    MAX_WORKED_ON,
    decayed_confidence,
    is_chronic,
    plan_consolidation,
)
from agent_service.app.application.graph_memory.facts import (
    FactTarget,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    STRUGGLES_WITH,
    WORKED_ON,
)
from agent_service.app.application.graph_memory.projection import profile_facts, project


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _fact(
        relation: str,
        kind: str,
        key: str,
        source: SourceKind = SourceKind.REVIEW,
        confidence: float = 0.8,
        occurrences: int = 1,
        age_days: float = 1.0,
        uuid: str | None = None,
        closed: bool = False,
) -> StoredFact:
    seen = NOW - timedelta(days=age_days)
    return StoredFact(
        edge_uuid=uuid or f"{relation}-{key}",
        user_id="u1",
        relation=relation,
        target=FactTarget(kind, key, key.replace("_", " ")),
        statement=f"The student: {relation} {key}.",
        source=source,
        confidence=confidence,
        occurred_at=seen,
        created_at=seen,
        last_seen_at=seen,
        occurrences=occurrences,
        valid_until=NOW if closed else None,
    )


def test_decay_is_half_life_not_linear():
    fresh = _fact(EXHIBITS, "error_pattern", "bare_except", age_days=0)
    half = _fact(EXHIBITS, "error_pattern", "bare_except", age_days=30)
    assert decayed_confidence(fresh, NOW) > 0.79
    assert abs(decayed_confidence(half, NOW) - 0.4) < 0.01


def test_repetition_slows_forgetting():
    once = _fact(EXHIBITS, "error_pattern", "bare_except", age_days=45, occurrences=1)
    often = _fact(EXHIBITS, "error_pattern", "bare_except", age_days=45, occurrences=5)
    assert decayed_confidence(often, NOW) > decayed_confidence(once, NOW)


def test_faded_fact_is_closed_not_deleted():
    stale = _fact(EXHIBITS, "error_pattern", "old_habit", confidence=0.4, age_days=400)
    assert decayed_confidence(stale, NOW) < FORGET_FLOOR

    plan = plan_consolidation([stale], now=NOW)
    assert [item.reason for item in plan.invalidate] == ["faded"]
    # Закрытие окна, а не удаление: история остаётся в графе.
    assert plan.prune == ()


def test_repeated_mistake_becomes_chronic_and_keeps_its_weight():
    repeated = _fact(
        EXHIBITS,
        "error_pattern",
        "bare_except",
        occurrences=CHRONIC_OCCURRENCES,
        age_days=60,
        confidence=0.8,
    )
    assert is_chronic(repeated)

    plan = plan_consolidation([repeated], now=NOW)
    update = next(item for item in plan.update if item.fact.edge_uuid == repeated.edge_uuid)
    assert update.chronic
    assert update.confidence >= 0.75
    assert plan.invalidate == ()


def test_mastery_closes_a_review_gap():
    gap = _fact(STRUGGLES_WITH, "skill", "testing", source=SourceKind.REVIEW, age_days=10)
    plan = plan_consolidation([gap], mastery={"testing": 0.92}, now=NOW)
    assert [item.reason for item in plan.invalidate] == ["mastery_recovered"]


def test_mastery_cannot_close_what_execution_showed():
    """Оценка модели знаний не сильнее наблюдения: тест упал — значит упал."""
    gap = _fact(STRUGGLES_WITH, "skill", "testing", source=SourceKind.HIDDEN_TESTS, age_days=10)
    plan = plan_consolidation([gap], mastery={"testing": 0.95}, now=NOW)
    assert plan.invalidate == ()


def test_dropped_mastery_closes_a_positive_claim():
    strength = _fact(DEMONSTRATES, "skill", "validation", age_days=10)
    plan = plan_consolidation([strength], mastery={"validation": 0.2}, now=NOW)
    assert [item.reason for item in plan.invalidate] == ["mastery_dropped"]


def test_fresh_fact_is_not_touched_by_mastery():
    gap = _fact(STRUGGLES_WITH, "skill", "testing", age_days=0.5)
    plan = plan_consolidation([gap], mastery={"testing": 0.95}, now=NOW)
    assert plan.invalidate == ()


def test_near_duplicate_patterns_are_merged():
    main = _fact(EXHIBITS, "error_pattern", "bare_except", occurrences=3, uuid="a")
    twin = _fact(EXHIBITS, "error_pattern", "bare_except_usage", occurrences=1, uuid="b")
    plan = plan_consolidation([main, twin], now=NOW)

    assert len(plan.merge) == 1
    merge = plan.merge[0]
    assert merge.keep.edge_uuid == "a"
    assert merge.drop.edge_uuid == "b"
    assert merge.occurrences == 4


def test_different_mistakes_are_not_merged():
    left = _fact(EXHIBITS, "error_pattern", "bare_except", uuid="a")
    right = _fact(EXHIBITS, "error_pattern", "missing_tests", uuid="b")
    assert plan_consolidation([left, right], now=NOW).merge == ()


def test_task_trail_is_pruned_but_knowledge_is_not():
    trail = [
        _fact(WORKED_ON, "task", f"t{index}", uuid=f"w{index}", age_days=index)
        for index in range(MAX_WORKED_ON + 5)
    ]
    plan = plan_consolidation(trail, now=NOW)
    assert len(plan.prune) == 5
    # Самые свежие задачи остаются.
    pruned = {item.target.key for item in plan.prune}
    assert "t0" not in pruned


def test_projection_puts_recurring_first_and_one_fact_per_skill():
    facts = [
        _fact(DEMONSTRATES, "skill", "validation", confidence=0.9),
        _fact(STRUGGLES_WITH, "skill", "error_handling", confidence=0.7),
        _fact(EXHIBITS, "error_pattern", "bare_except", occurrences=4),
        _fact(STRUGGLES_WITH, "skill", "error_handling", uuid="dup", confidence=0.6),
        _fact(WORKED_ON, "task", "t1"),
    ]
    projected = project(facts, now=NOW)
    relations = [item.relation for item in projected]

    assert relations[0] == EXHIBITS
    assert projected[0].chronic
    # След задач в подсказку не идёт, и навык не дублируется.
    assert WORKED_ON not in relations
    assert relations.count(STRUGGLES_WITH) == 1

    rendered = profile_facts(facts, now=NOW)
    assert "recurring ×4" in rendered[0]
