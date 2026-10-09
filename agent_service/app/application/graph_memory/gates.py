from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from agent_service.app.application.decisions.questions import (
    Answers,
    Choice,
    Noul,
    Question,
)
from agent_service.app.application.graph_memory.facts import (
    FactOperation,
    GraphFact,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import SKILL_BY_ID


KEEP_THRESHOLD = 0.55
OPERATION_CONFIDENCE = 0.6

OPERATION_OPTIONS: dict[str, str] = {
    FactOperation.ADD.value: (
        "This is new and durable knowledge about the student. Nothing in memory says it yet."
    ),
    FactOperation.REINFORCE.value: (
        "Memory already holds this fact. The episode is one more occurrence of the same thing, "
        "so the existing fact should get stronger instead of being duplicated."
    ),
    FactOperation.INVALIDATE.value: (
        "The episode shows the opposite of what memory holds: the student no longer makes this "
        "mistake, or the recorded gap is closed. The old fact stops being true from now on."
    ),
    FactOperation.SKIP.value: (
        "Not worth storing: a one-off detail, a restatement of the task, or something the "
        "episode does not actually support."
    ),
}


@dataclass(frozen=True, slots=True)
class GateDecision:
    operation: FactOperation
    keep_probability: float | None = None
    source: str = "rules"
    reason: str = ""

    @property
    def from_model(self) -> bool:
        return self.source == "jev"


def gate_questions(facts: Sequence[GraphFact]) -> list[Question]:
    questions: list[Question] = []
    for index, fact in enumerate(facts):
        questions.append(
            Noul(
                name=f"keep_{index}",
                instructions=(
                    f"Fact #{index} is about to enter the long-term memory of a programming "
                    "student. Will it still help when the student takes a similar task in two weeks?"
                ),
                if_true=(
                    "It names a stable property of this student: a mistake they repeat, a gap "
                    "confirmed by evidence, a skill they clearly handle, or how they want to be helped."
                ),
                if_false=(
                    "It is a one-off detail of this task, a restatement of the brief, a score, "
                    "or a guess the episode does not support."
                ),
            )
        )
        questions.append(
            Choice(
                name=f"op_{index}",
                instructions=(
                    f"What should happen to fact #{index} given what memory already holds?"
                ),
                options=dict(OPERATION_OPTIONS),
            )
        )
    return questions


def gate_state(
        facts: Sequence[GraphFact],
        existing: Mapping[str, Sequence[StoredFact]],
        episode_body: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "episode": _clip(episode_body, 1500),
        "facts": {},
    }
    for index, fact in enumerate(facts):
        held = list(existing.get(fact.key, ()))
        opposite = [
            item
            for key, items in existing.items()
            for item in items
            if key != fact.key and item.target.key == fact.target.key
        ]
        payload["facts"][f"#{index}"] = {
            "statement": fact.statement,
            "relation": fact.relation,
            "about": _about(fact),
            "evidence": fact.source.value,
            "memory_holds_this": [item.statement for item in held][:2],
            "memory_holds_opposite": [item.statement for item in opposite][:2],
        }
    return payload


def read_gate(
        answers: Answers,
        index: int,
        fallback: FactOperation,
        min_confidence: float = OPERATION_CONFIDENCE,
) -> GateDecision:
    keep = answers.noul(f"keep_{index}")
    if keep is None:
        return GateDecision(fallback, source="rules", reason="no_answer")
    if keep < KEEP_THRESHOLD:
        return GateDecision(
            FactOperation.SKIP,
            keep_probability=keep,
            source="jev",
            reason="below_keep_threshold",
        )
    choice = answers.choice(f"op_{index}", min_confidence=min_confidence)
    if choice is None:
        return GateDecision(
            fallback,
            keep_probability=keep,
            source="rules",
            reason="low_operation_confidence",
        )
    try:
        operation = FactOperation(choice.value)
    except ValueError:
        return GateDecision(fallback, keep_probability=keep, source="rules", reason="unknown_option")
    return GateDecision(operation, keep_probability=keep, source="jev", reason="model")


def heuristic_keep(fact: GraphFact) -> bool:
    if fact.source is SourceKind.HIDDEN_TESTS:
        return True
    floor = 0.7 if fact.source is SourceKind.CHAT else 0.5
    return fact.confidence >= floor


def _about(fact: GraphFact) -> str:
    if fact.target.kind == "skill":
        skill = SKILL_BY_ID.get(fact.target.key)
        return skill.name if skill else fact.target.key
    return fact.target.display_name()


def _clip(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"
