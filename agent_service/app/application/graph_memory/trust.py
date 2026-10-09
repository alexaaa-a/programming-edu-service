from dataclasses import dataclass
from datetime import datetime

from agent_service.app.application.graph_memory.facts import (
    FactOperation,
    GraphFact,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import RELATION_BY_NAME


TRUST_RANK: dict[SourceKind, int] = {
    SourceKind.HIDDEN_TESTS: 3,
    SourceKind.REVIEW: 2,
    SourceKind.TRAJECTORY: 2,
    SourceKind.CHAT: 1,
}
CONFIDENCE_CEILING: dict[SourceKind, float] = {
    SourceKind.HIDDEN_TESTS: 1.0,
    SourceKind.REVIEW: 0.9,
    SourceKind.TRAJECTORY: 0.85,
    SourceKind.CHAT: 0.6,
}


def trust_rank(source: SourceKind) -> int:
    return TRUST_RANK.get(source, 1)


def cap_confidence(fact: GraphFact) -> GraphFact:
    ceiling = CONFIDENCE_CEILING.get(fact.source, 0.6)
    if fact.confidence <= ceiling:
        return fact
    return fact.with_confidence(ceiling)


def may_override(incoming: SourceKind, existing: SourceKind) -> bool:
    return trust_rank(incoming) >= trust_rank(existing)


@dataclass(frozen=True, slots=True)
class Resolution:
    operation: FactOperation
    invalidate: tuple[StoredFact, ...] = ()
    same: tuple[StoredFact, ...] = ()
    reason: str = ""


def resolve(
        incoming: GraphFact,
        existing: list[StoredFact],
        now: datetime | None = None,
) -> Resolution:
    moment = now or incoming.occurred_at
    valid = [item for item in existing if item.is_valid]

    same = tuple(item for item in valid if item.key == incoming.key)
    if same:
        held = same[0]
        if not may_override(incoming.source, held.source) and incoming.source is SourceKind.CHAT:
            return Resolution(FactOperation.SKIP, same=same, reason="weaker_source_repeat")
        return Resolution(FactOperation.REINFORCE, same=same, reason="already_known")

    opposite_name = RELATION_BY_NAME[incoming.relation].contradicts if incoming.relation in RELATION_BY_NAME else ""
    if not opposite_name:
        return Resolution(FactOperation.ADD, reason="new_fact")

    opposite_key = f"{opposite_name}|{incoming.target.kind}:{incoming.target.key}"
    conflicting = [item for item in valid if item.key == opposite_key]
    if not conflicting:
        return Resolution(FactOperation.ADD, reason="new_fact")

    blocked = [item for item in conflicting if not may_override(incoming.source, item.source)]
    if blocked:
        return Resolution(FactOperation.SKIP, reason="weaker_than_existing")

    stale = [item for item in conflicting if _not_newer(item, moment)]
    if stale:
        return Resolution(FactOperation.SKIP, reason="older_than_existing")

    return Resolution(
        FactOperation.ADD,
        invalidate=tuple(conflicting),
        reason="contradiction_resolved",
    )


def _not_newer(existing: StoredFact, moment: datetime) -> bool:
    seen = existing.last_seen_at or existing.occurred_at
    if seen.tzinfo is None or moment.tzinfo is None:
        return False
    return moment < seen
