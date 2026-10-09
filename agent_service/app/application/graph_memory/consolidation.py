from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

from agent_service.app.application.graph_memory.facts import (
    SourceKind,
    StoredFact,
    utc_now,
)
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    PREFERS,
    STRUGGLES_WITH,
    WORKED_ON,
)
from agent_service.app.application.graph_memory.trust import may_override


CHRONIC_OCCURRENCES = 3

HALF_LIFE_DAYS: Mapping[str, float] = {
    EXHIBITS: 30.0,
    STRUGGLES_WITH: 45.0,
    DEMONSTRATES: 60.0,
    PREFERS: 120.0,
}

FORGET_FLOOR = 0.2
MAX_WORKED_ON = 30

MASTERY_LEARNED = 0.8
MASTERY_LOST = 0.35
MIN_AGE_FOR_MASTERY_DAYS = 3.0


@dataclass(frozen=True, slots=True)
class Invalidation:
    fact: StoredFact
    reason: str


@dataclass(frozen=True, slots=True)
class ConfidenceUpdate:
    fact: StoredFact
    confidence: float
    chronic: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Merge:
    keep: StoredFact
    drop: StoredFact
    occurrences: int
    reason: str = "duplicate_pattern"


@dataclass(frozen=True, slots=True)
class ConsolidationPlan:
    invalidate: tuple[Invalidation, ...] = ()
    update: tuple[ConfidenceUpdate, ...] = ()
    merge: tuple[Merge, ...] = ()
    prune: tuple[StoredFact, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.invalidate or self.update or self.merge or self.prune)

    @property
    def size(self) -> int:
        return len(self.invalidate) + len(self.update) + len(self.merge) + len(self.prune)


def plan_consolidation(
        facts: Sequence[StoredFact],
        mastery: Mapping[str, float] | None = None,
        now: datetime | None = None,
) -> ConsolidationPlan:
    moment = now or utc_now()
    valid = [fact for fact in facts if fact.is_valid]

    merges = _plan_merges(valid)
    merged_away = {item.drop.edge_uuid for item in merges}
    working = [fact for fact in valid if fact.edge_uuid not in merged_away]

    invalidations: list[Invalidation] = []
    updates: list[ConfidenceUpdate] = []

    for fact in working:
        decision = _decay_or_promote(fact, moment)
        if isinstance(decision, Invalidation):
            invalidations.append(decision)
        elif decision is not None:
            updates.append(decision)

    closed = {item.fact.edge_uuid for item in invalidations}
    invalidations.extend(
        item
        for item in _plan_mastery_reconciliation(working, mastery or {}, moment)
        if item.fact.edge_uuid not in closed
    )

    return ConsolidationPlan(
        invalidate=tuple(invalidations),
        update=tuple(updates),
        merge=tuple(merges),
        prune=tuple(_plan_prune(working)),
    )


def decayed_confidence(fact: StoredFact, now: datetime | None = None) -> float:
    half_life = HALF_LIFE_DAYS.get(fact.relation)
    if half_life is None:
        return fact.confidence
    occurrences = max(1, int(fact.occurrences))
    effective = half_life * (1.0 + 0.5 * (occurrences - 1))
    age = fact.age_days(now)
    return float(fact.confidence) * (0.5 ** (age / effective))


def is_chronic(fact: StoredFact) -> bool:
    return fact.relation in {EXHIBITS, STRUGGLES_WITH} and fact.occurrences >= CHRONIC_OCCURRENCES


def _decay_or_promote(
        fact: StoredFact,
        now: datetime,
) -> Invalidation | ConfidenceUpdate | None:
    if fact.relation == WORKED_ON:
        return None
    fresh = decayed_confidence(fact, now)
    if fresh < FORGET_FLOOR:
        return Invalidation(fact, reason="faded")
    chronic = is_chronic(fact)
    if chronic:
        fresh = max(fresh, 0.75)
    if abs(fresh - fact.confidence) < 0.02 and not chronic:
        return None
    return ConfidenceUpdate(
        fact=fact,
        confidence=round(fresh, 3),
        chronic=chronic,
        reason="chronic" if chronic else "decay",
    )


def _plan_mastery_reconciliation(
        facts: Sequence[StoredFact],
        mastery: Mapping[str, float],
        now: datetime,
) -> list[Invalidation]:
    if not mastery:
        return []
    out: list[Invalidation] = []
    for fact in facts:
        if fact.target.kind != "skill":
            continue
        level = mastery.get(fact.target.key)
        if level is None:
            continue
        if fact.age_days(now) < MIN_AGE_FOR_MASTERY_DAYS:
            continue
        if not may_override(SourceKind.TRAJECTORY, fact.source):
            continue
        if fact.relation == STRUGGLES_WITH and level >= MASTERY_LEARNED:
            out.append(Invalidation(fact, reason="mastery_recovered"))
        elif fact.relation == DEMONSTRATES and level <= MASTERY_LOST:
            out.append(Invalidation(fact, reason="mastery_dropped"))
    return out


def _plan_merges(facts: Sequence[StoredFact]) -> list[Merge]:
    patterns = [fact for fact in facts if fact.target.kind == "error_pattern"]
    merges: list[Merge] = []
    dropped: set[str] = set()
    for index, left in enumerate(patterns):
        if left.edge_uuid in dropped:
            continue
        for right in patterns[index + 1:]:
            if right.edge_uuid in dropped or left.target.key == right.target.key:
                continue
            if not _same_pattern(left.target.key, right.target.key):
                continue
            keep, drop = _pick_survivor(left, right)
            dropped.add(drop.edge_uuid)
            merges.append(
                Merge(
                    keep=keep,
                    drop=drop,
                    occurrences=int(keep.occurrences) + int(drop.occurrences),
                )
            )
    return merges


def _same_pattern(left: str, right: str) -> bool:
    a, b = set(left.split("_")), set(right.split("_"))
    if not a or not b:
        return False
    if a <= b or b <= a:
        return True
    overlap = len(a & b) / len(a | b)
    return overlap >= 0.6


def _pick_survivor(left: StoredFact, right: StoredFact) -> tuple[StoredFact, StoredFact]:
    if left.occurrences != right.occurrences:
        return (left, right) if left.occurrences > right.occurrences else (right, left)
    left_seen = left.last_seen_at or left.occurred_at
    right_seen = right.last_seen_at or right.occurred_at
    return (left, right) if left_seen >= right_seen else (right, left)


def _plan_prune(facts: Sequence[StoredFact]) -> list[StoredFact]:
    worked = [fact for fact in facts if fact.relation == WORKED_ON]
    if len(worked) <= MAX_WORKED_ON:
        return []
    worked.sort(key=lambda item: item.last_seen_at or item.occurred_at, reverse=True)
    return worked[MAX_WORKED_ON:]


@dataclass(frozen=True, slots=True)
class ConsolidationReport:
    students: int = 0
    invalidated: int = 0
    updated: int = 0
    merged: int = 0
    pruned: int = 0
    failed: int = 0
    details: list[str] = field(default_factory=list)

    def plus(self, plan: ConsolidationPlan) -> "ConsolidationReport":
        return ConsolidationReport(
            students=self.students + 1,
            invalidated=self.invalidated + len(plan.invalidate),
            updated=self.updated + len(plan.update),
            merged=self.merged + len(plan.merge),
            pruned=self.pruned + len(plan.prune),
            failed=self.failed,
            details=self.details,
        )

    def with_failure(self, detail: str) -> "ConsolidationReport":
        return ConsolidationReport(
            students=self.students,
            invalidated=self.invalidated,
            updated=self.updated,
            merged=self.merged,
            pruned=self.pruned,
            failed=self.failed + 1,
            details=[*self.details, detail][:20],
        )


def recent_window(days: float, now: datetime | None = None) -> datetime:
    return (now or utc_now()) - timedelta(days=days)


def chronic_facts(facts: Iterable[StoredFact]) -> list[StoredFact]:
    return [fact for fact in facts if fact.is_valid and is_chronic(fact)]
