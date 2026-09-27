from abc import abstractmethod
from typing import Protocol


class AdminRoleGatewayInterface(Protocol):
    @abstractmethod
    async def get_my_role(self, authorization: str) -> str:
        raise NotImplementedError
