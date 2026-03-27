from abc import ABC, abstractmethod
from typing import Any

from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.interfaces import MemoryInterface


class BaseAgent(ABC):
    def __init__(
        self,
        llm: LLMInterface,
        memory: MemoryInterface | None = None,
    ) -> None:
        self._llm = llm
        self._memory = memory

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

