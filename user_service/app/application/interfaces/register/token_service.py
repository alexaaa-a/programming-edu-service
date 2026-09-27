from abc import abstractmethod
from typing import Protocol


class TokenServiceInterface(Protocol):
    @abstractmethod
    def create_token(self, user_id: int, token_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def decode_token(self, token: str) -> int | None:
        raise NotImplementedError

    @abstractmethod
    def decode_refresh_token(self, token: str) -> int | None:
        raise NotImplementedError
