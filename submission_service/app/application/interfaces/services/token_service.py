from abc import abstractmethod
from typing import Protocol


class TokenServiceInterface(Protocol):

    @abstractmethod
    def decode_token(self, token: str) -> int | None:
        raise NotImplementedError
