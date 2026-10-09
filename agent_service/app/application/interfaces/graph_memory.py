from datetime import datetime
from typing import Protocol, Sequence

from agent_service.app.application.graph_memory.facts import (
    GraphFact,
    GraphWriteResult,
    StoredFact,
)
from agent_service.app.application.graph_memory.recipes import ReadIntent


class GraphMemoryInterface(Protocol):
    @property
    def enabled(self) -> bool:
        raise NotImplementedError

    async def ensure_schema(self) -> None:
        raise NotImplementedError

    async def write(self, fact: GraphFact) -> GraphWriteResult:
        raise NotImplementedError

    async def invalidate(self, fact: StoredFact, at: datetime, reason: str = "") -> bool:
        raise NotImplementedError

    async def update_confidence(
            self,
            fact: StoredFact,
            confidence: float,
            chronic: bool = False,
    ) -> bool:
        raise NotImplementedError

    async def merge_facts(self, keep: StoredFact, drop: StoredFact, occurrences: int) -> bool:
        raise NotImplementedError

    async def facts_for(
            self,
            user_id: str,
            intent: ReadIntent,
            query: str = "",
            skill_ids: Sequence[str] = (),
            limit: int | None = None,
    ) -> list[StoredFact]:
        raise NotImplementedError

    async def all_facts(self, user_id: str, include_closed: bool = False) -> list[StoredFact]:
        raise NotImplementedError

    async def known_pattern_slugs(self, user_id: str) -> list[str]:
        raise NotImplementedError

    async def remember_mastery(self, user_id: str, mastery: dict[str, float]) -> None:
        raise NotImplementedError

    async def mastery_of(self, user_id: str) -> dict[str, float]:
        raise NotImplementedError

    async def students_with_memory(self, limit: int = 200) -> list[str]:
        raise NotImplementedError

    async def forget_student(self, user_id: str) -> int:
        raise NotImplementedError
