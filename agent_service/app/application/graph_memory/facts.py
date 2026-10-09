from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from agent_service.app.application.graph_memory.ontology import (
    ERROR_PATTERN,
    PREFERENCE,
    SKILL,
    TASK,
)


class SourceKind(str, Enum):
    HIDDEN_TESTS = "hidden_tests"
    REVIEW = "review"
    TRAJECTORY = "trajectory"
    CHAT = "chat"


class FactOperation(str, Enum):
    ADD = "add"
    REINFORCE = "reinforce"
    INVALIDATE = "invalidate"
    SKIP = "skip"


class EpisodeKind(str, Enum):
    REVIEW = "review"
    CHAT = "chat"


TARGET_LABELS: Mapping[str, str] = {
    "skill": SKILL,
    "error_pattern": ERROR_PATTERN,
    "task": TASK,
    "preference": PREFERENCE,
}


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class FactTarget:
    kind: str
    key: str
    name: str = ""

    @property
    def label(self) -> str:
        return TARGET_LABELS.get(self.kind, "")

    def display_name(self) -> str:
        return self.name or self.key.replace("_", " ")


@dataclass(frozen=True, slots=True)
class GraphFact:
    user_id: str
    relation: str
    target: FactTarget
    statement: str
    source: SourceKind
    operation: FactOperation = FactOperation.ADD
    confidence: float = 0.7
    occurred_at: datetime = field(default_factory=utc_now)
    task_id: str | None = None
    submission_id: str | None = None
    session_id: str | None = None
    writer: str = "memory_curator"

    @property
    def key(self) -> str:
        return f"{self.relation}|{self.target.kind}:{self.target.key}"

    def with_operation(self, operation: FactOperation) -> "GraphFact":
        return replace_fact(self, operation=operation)

    def with_confidence(self, confidence: float) -> "GraphFact":
        return replace_fact(self, confidence=max(0.0, min(1.0, float(confidence))))

    def evidence(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_kind": self.source.value,
            "writer": self.writer,
            "confidence": round(float(self.confidence), 3),
        }
        if self.task_id:
            data["task_id"] = str(self.task_id)
        if self.submission_id:
            data["submission_id"] = str(self.submission_id)
        if self.session_id:
            data["session_id"] = str(self.session_id)
        return data


def replace_fact(fact: GraphFact, **changes: Any) -> GraphFact:
    data = {
        "user_id": fact.user_id,
        "relation": fact.relation,
        "target": fact.target,
        "statement": fact.statement,
        "source": fact.source,
        "operation": fact.operation,
        "confidence": fact.confidence,
        "occurred_at": fact.occurred_at,
        "task_id": fact.task_id,
        "submission_id": fact.submission_id,
        "session_id": fact.session_id,
        "writer": fact.writer,
    }
    data.update(changes)
    return GraphFact(**data)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class StoredFact:
    edge_uuid: str
    user_id: str
    relation: str
    target: FactTarget
    statement: str
    source: SourceKind
    confidence: float
    occurred_at: datetime
    created_at: datetime
    valid_until: datetime | None = None
    occurrences: int = 1
    last_seen_at: datetime | None = None
    task_id: str | None = None
    submission_id: str | None = None
    score: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.relation}|{self.target.kind}:{self.target.key}"

    @property
    def is_valid(self) -> bool:
        return self.valid_until is None

    def age_days(self, now: datetime | None = None) -> float:
        moment = now or utc_now()
        seen = self.last_seen_at or self.occurred_at
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        return max(0.0, (moment - seen).total_seconds() / 86_400.0)


@dataclass(frozen=True, slots=True)
class MemoryEpisode:
    episode_id: str
    kind: EpisodeKind
    user_id: str
    occurred_at: datetime
    body: str
    task_id: str | None = None
    submission_id: str | None = None
    session_id: str | None = None
    task_title: str = ""
    observations: list[dict[str, Any]] = field(default_factory=list)
    mastery: dict[str, float] = field(default_factory=dict)

    def as_document(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "kind": self.kind.value,
            "user_id": self.user_id,
            "occurred_at": self.occurred_at,
            "body": self.body,
            "task_id": self.task_id,
            "submission_id": self.submission_id,
            "session_id": self.session_id,
            "task_title": self.task_title,
            "observations": list(self.observations),
            "mastery": dict(self.mastery),
        }

    @classmethod
    def from_document(cls, doc: Mapping[str, Any]) -> "MemoryEpisode":
        occurred = doc.get("occurred_at")
        if isinstance(occurred, datetime):
            moment = occurred if occurred.tzinfo else occurred.replace(tzinfo=timezone.utc)
        else:
            moment = utc_now()
        raw_kind = str(doc.get("kind") or EpisodeKind.REVIEW.value)
        kind = EpisodeKind(raw_kind) if raw_kind in {k.value for k in EpisodeKind} else EpisodeKind.REVIEW
        raw_mastery = doc.get("mastery")
        mastery = (
            {str(k): float(v) for k, v in raw_mastery.items() if _is_number(v)}
            if isinstance(raw_mastery, Mapping)
            else {}
        )
        raw_observations = doc.get("observations")
        observations = [dict(item) for item in raw_observations if isinstance(item, Mapping)] \
            if isinstance(raw_observations, list) else []
        return cls(
            episode_id=str(doc.get("episode_id") or ""),
            kind=kind,
            user_id=str(doc.get("user_id") or ""),
            occurred_at=moment,
            body=str(doc.get("body") or ""),
            task_id=_opt_str(doc.get("task_id")),
            submission_id=_opt_str(doc.get("submission_id")),
            session_id=_opt_str(doc.get("session_id")),
            task_title=str(doc.get("task_title") or ""),
            observations=observations,
            mastery=mastery,
        )


@dataclass(frozen=True, slots=True)
class GraphWriteResult:
    operation: FactOperation
    edge_uuid: str = ""
    invalidated: int = 0

    @property
    def written(self) -> bool:
        return self.operation is not FactOperation.SKIP


def _opt_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
