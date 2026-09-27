from abc import abstractmethod
from typing import Protocol


class CacheInterface(Protocol):
    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError
