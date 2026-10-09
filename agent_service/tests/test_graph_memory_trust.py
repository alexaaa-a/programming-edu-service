"""Иерархия доверия и типизированные ворота записи."""

from datetime import datetime, timedelta, timezone

from agent_service.app.application.decisions.questions import (
    Answers,
    Choice,
    ChoiceAnswer,
    Noul,
)
from agent_service.app.application.graph_memory.facts import (
    FactOperation,
    FactTarget,
    GraphFact,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.gates import (
    GateDecision,
    gate_questions,
    gate_state,
    heuristic_keep,
    read_gate,
)
from agent_service.app.application.graph_memory.ontology import DEMONSTRATES, STRUGGLES_WITH
from agent_service.app.application.graph_memory.trust import (
    cap_confidence,
    may_override,
    resolve,
    trust_rank,
)


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
SKILL = FactTarget("skill", "error_handling", "Error handling")


def _incoming(relation: str, source: SourceKind, when: datetime = NOW, confidence: float = 0.8) -> GraphFact:
    return GraphFact(
        user_id="u1",
        relation=relation,
        target=SKILL,
        statement="The student handles errors badly.",
        source=source,
        confidence=confidence,
        occurred_at=when,
    )


def _stored(relation: str, source: SourceKind, when: datetime = NOW - timedelta(days=2)) -> StoredFact:
    return StoredFact(
        edge_uuid=f"e-{relation}",
        user_id="u1",
        relation=relation,
        target=SKILL,
        statement="stored",
        source=source,
        confidence=0.8,
        occurred_at=when,
        created_at=when,
        last_seen_at=when,
    )


def test_trust_order_puts_execution_first():
    assert trust_rank(SourceKind.HIDDEN_TESTS) > trust_rank(SourceKind.REVIEW)
    assert trust_rank(SourceKind.REVIEW) > trust_rank(SourceKind.CHAT)
    assert may_override(SourceKind.HIDDEN_TESTS, SourceKind.REVIEW)
    assert may_override(SourceKind.REVIEW, SourceKind.REVIEW)
    assert not may_override(SourceKind.CHAT, SourceKind.REVIEW)


def test_confidence_is_capped_by_source():
    loud_chat = _incoming(STRUGGLES_WITH, SourceKind.CHAT, confidence=0.99)
    assert cap_confidence(loud_chat).confidence <= 0.6
    tests = _incoming(STRUGGLES_WITH, SourceKind.HIDDEN_TESTS, confidence=0.95)
    assert cap_confidence(tests).confidence == 0.95


def test_known_fact_is_reinforced_not_duplicated():
    decision = resolve(
        _incoming(STRUGGLES_WITH, SourceKind.REVIEW),
        [_stored(STRUGGLES_WITH, SourceKind.REVIEW)],
    )
    assert decision.operation is FactOperation.REINFORCE


def test_chat_cannot_reinforce_what_execution_recorded():
    decision = resolve(
        _incoming(STRUGGLES_WITH, SourceKind.CHAT),
        [_stored(STRUGGLES_WITH, SourceKind.HIDDEN_TESTS)],
    )
    assert decision.operation is FactOperation.SKIP
    assert decision.reason == "weaker_source_repeat"


def test_execution_closes_a_review_judgement():
    decision = resolve(
        _incoming(DEMONSTRATES, SourceKind.HIDDEN_TESTS),
        [_stored(STRUGGLES_WITH, SourceKind.REVIEW)],
    )
    assert decision.operation is FactOperation.ADD
    assert [item.relation for item in decision.invalidate] == [STRUGGLES_WITH]


def test_chat_cannot_close_what_execution_showed():
    """Главное правило: «я всё исправил» не стирает упавший тест."""
    decision = resolve(
        _incoming(DEMONSTRATES, SourceKind.CHAT),
        [_stored(STRUGGLES_WITH, SourceKind.HIDDEN_TESTS)],
    )
    assert decision.operation is FactOperation.SKIP
    assert decision.reason == "weaker_than_existing"


def test_older_observation_does_not_overwrite_newer():
    decision = resolve(
        _incoming(DEMONSTRATES, SourceKind.REVIEW, when=NOW - timedelta(days=10)),
        [_stored(STRUGGLES_WITH, SourceKind.REVIEW, when=NOW)],
    )
    assert decision.operation is FactOperation.SKIP
    assert decision.reason == "older_than_existing"


def test_gate_questions_are_typed_and_closed():
    facts = [_incoming(STRUGGLES_WITH, SourceKind.REVIEW)]
    questions = gate_questions(facts)
    assert [q.name for q in questions] == ["keep_0", "op_0"]
    assert isinstance(questions[0], Noul)
    assert isinstance(questions[1], Choice)
    # Модель выбирает только из наших операций, пятую придумать нельзя.
    assert set(questions[1].options) == {item.value for item in FactOperation}


def test_gate_state_shows_what_memory_already_holds():
    fact = _incoming(STRUGGLES_WITH, SourceKind.REVIEW)
    state = gate_state([fact], {fact.key: [_stored(STRUGGLES_WITH, SourceKind.REVIEW)]}, "episode text")
    entry = state["facts"]["#0"]
    assert entry["about"] == "Error handling"
    assert entry["memory_holds_this"] == ["stored"]
    assert state["episode"] == "episode text"


def test_read_gate_respects_the_keep_threshold():
    answers = Answers(items={"keep_0": 0.2, "op_0": ChoiceAnswer("add", 0.99, {})})
    decision = read_gate(answers, 0, FactOperation.ADD)
    assert decision.operation is FactOperation.SKIP
    assert decision.reason == "below_keep_threshold"


def test_read_gate_takes_a_confident_choice():
    answers = Answers(items={"keep_0": 0.9, "op_0": ChoiceAnswer("invalidate", 0.9, {})})
    decision = read_gate(answers, 0, FactOperation.ADD, min_confidence=0.6)
    assert decision.operation is FactOperation.INVALIDATE
    assert decision.from_model


def test_read_gate_ignores_an_option_outside_the_enum():
    answers = Answers(items={"keep_0": 0.9, "op_0": ChoiceAnswer("rewrite_everything", 0.9, {})})
    decision = read_gate(answers, 0, FactOperation.ADD)
    assert decision.operation is FactOperation.ADD
    assert decision.reason == "unknown_option"


def test_read_gate_falls_back_when_model_is_unsure():
    answers = Answers(items={"keep_0": 0.9, "op_0": ChoiceAnswer("invalidate", 0.2, {})})
    decision = read_gate(answers, 0, FactOperation.ADD, min_confidence=0.6)
    assert decision.operation is FactOperation.ADD
    assert decision.source == "rules"


def test_read_gate_without_answers_keeps_the_rule():
    decision = read_gate(Answers(items={}), 0, FactOperation.REINFORCE)
    assert decision == GateDecision(FactOperation.REINFORCE, source="rules", reason="no_answer")


def test_heuristic_keep_is_strict_about_chat():
    assert heuristic_keep(_incoming(STRUGGLES_WITH, SourceKind.HIDDEN_TESTS, confidence=0.1))
    assert heuristic_keep(_incoming(STRUGGLES_WITH, SourceKind.REVIEW, confidence=0.55))
    assert not heuristic_keep(_incoming(STRUGGLES_WITH, SourceKind.CHAT, confidence=0.55))
