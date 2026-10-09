from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from agent_service.app.application.graph_memory.consolidation import is_chronic
from agent_service.app.application.graph_memory.facts import StoredFact, utc_now
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    PREFERS,
    STRUGGLES_WITH,
    WORKED_ON,
)


MAX_PROFILE_FACTS = 5
MAX_FACT_CHARS = 180
RELATION_PRIORITY: dict[str, int] = {
    EXHIBITS: 0,
    STRUGGLES_WITH: 1,
    PREFERS: 2,
    DEMONSTRATES: 3,
    WORKED_ON: 9,
}


@dataclass(frozen=True, slots=True)
class ProjectedFact:
    text: str
    relation: str
    skill_id: str
    chronic: bool
    occurrences: int
    confidence: float
    source: str

    def rendered(self) -> str:
        marks: list[str] = []
        if self.chronic:
            marks.append(f"recurring ×{self.occurrences}")
        if self.source:
            marks.append(self.source.replace("_", " "))
        suffix = f" [{', '.join(marks)}]" if marks else ""
        return f"{self.text}{suffix}"


def rank_facts(
        facts: Sequence[StoredFact],
        now: datetime | None = None,
) -> list[StoredFact]:
    moment = now or utc_now()

    def sort_key(fact: StoredFact) -> tuple[int, int, float, float]:
        return (
            RELATION_PRIORITY.get(fact.relation, 5),
            0 if is_chronic(fact) else 1,
            -float(fact.confidence),
            fact.age_days(moment),
        )

    return sorted([fact for fact in facts if fact.is_valid], key=sort_key)


def project(
        facts: Sequence[StoredFact],
        limit: int = MAX_PROFILE_FACTS,
        now: datetime | None = None,
) -> list[ProjectedFact]:
    out: list[ProjectedFact] = []
    seen_skills: set[str] = set()
    for fact in rank_facts(facts, now):
        if fact.relation == WORKED_ON:
            continue
        skill_id = fact.target.key if fact.target.kind == "skill" else ""
        if skill_id and skill_id in seen_skills:
            continue
        if skill_id:
            seen_skills.add(skill_id)
        out.append(
            ProjectedFact(
                text=_clip(fact.statement, MAX_FACT_CHARS),
                relation=fact.relation,
                skill_id=skill_id,
                chronic=is_chronic(fact),
                occurrences=int(fact.occurrences),
                confidence=round(float(fact.confidence), 2),
                source=fact.source.value,
            )
        )
        if len(out) >= limit:
            break
    return out


def profile_facts(
        facts: Sequence[StoredFact],
        limit: int = MAX_PROFILE_FACTS,
        now: datetime | None = None,
) -> list[str]:
    return [item.rendered() for item in project(facts, limit=limit, now=now)]


def worked_on_task_ids(facts: Sequence[StoredFact], limit: int = 5) -> list[str]:
    tasks = [fact for fact in facts if fact.relation == WORKED_ON and fact.is_valid]
    tasks.sort(key=lambda item: item.last_seen_at or item.occurred_at, reverse=True)
    return [fact.target.key for fact in tasks[:limit]]


def _clip(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"
