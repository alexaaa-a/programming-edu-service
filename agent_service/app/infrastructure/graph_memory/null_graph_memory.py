from datetime import datetime
from typing import Sequence

from agent_service.app.application.graph_memory.facts import (
    FactOperation,
    GraphFact,
    GraphWriteResult,
    StoredFact,
)
from agent_service.app.application.graph_memory.recipes import ReadIntent
from agent_service.app.application.interfaces.graph_memory import GraphMemoryInterface


class NullGraphMemory(GraphMemoryInterface):
    @property
    def enabled(self) -> bool:
        return False

    async def ensure_schema(self) -> None:
        return None

    async def write(self, fact: GraphFact) -> GraphWriteResult:
        return GraphWriteResult(FactOperation.SKIP)

    async def invalidate(self, fact: StoredFact, at: datetime, reason: str = "") -> bool:
        return False

    async def update_confidence(
            self,
            fact: StoredFact,
            confidence: float,
            chronic: bool = False,
    ) -> bool:
        return False

    async def merge_facts(self, keep: StoredFact, drop: StoredFact, occurrences: int) -> bool:
        return False

    async def facts_for(
            self,
            user_id: str,
            intent: ReadIntent,
            query: str = "",
            skill_ids: Sequence[str] = (),
            limit: int | None = None,
    ) -> list[StoredFact]:
        return []

    async def all_facts(self, user_id: str, include_closed: bool = False) -> list[StoredFact]:
        return []

    async def known_pattern_slugs(self, user_id: str) -> list[str]:
        return []

    async def remember_mastery(self, user_id: str, mastery: dict[str, float]) -> None:
        return None

    async def mastery_of(self, user_id: str) -> dict[str, float]:
        return {}

    async def students_with_memory(self, limit: int = 200) -> list[str]:
        return []

    async def forget_student(self, user_id: str) -> int:
        return 0
