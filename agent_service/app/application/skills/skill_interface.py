from __future__ import annotations

from typing import Any, Protocol


class AgentSkill(Protocol):
    name: str
    description: str

    async def run(self, **kwargs: Any) -> Any: ...

