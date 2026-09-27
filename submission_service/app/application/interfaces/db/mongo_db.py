from abc import abstractmethod
from typing import Protocol


class MongoDBInterface(Protocol):
    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError
