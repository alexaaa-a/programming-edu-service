from datetime import datetime
from typing import Protocol

from agent_service.app.application.graph_memory.facts import MemoryEpisode


class MemoryEpisodeQueue(Protocol):
    async def enqueue(self, episode: MemoryEpisode) -> bool:
        raise NotImplementedError

    async def claim(self, limit: int, now: datetime | None = None) -> list[MemoryEpisode]:
        raise NotImplementedError

    async def mark_done(self, episode_id: str, facts_written: int = 0) -> None:
        raise NotImplementedError

    async def mark_failed(self, episode_id: str, reason: str) -> None:
        raise NotImplementedError

    async def pending_count(self) -> int:
        raise NotImplementedError
