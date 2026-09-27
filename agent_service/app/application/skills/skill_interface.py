from typing import Any, Protocol


class AgentSkill(Protocol):
    name: str
    description: str

    async def run(self, **kwargs: Any) -> Any: ...

