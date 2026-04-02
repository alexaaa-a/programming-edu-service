from typing import Protocol


class HealthDependenciesChecker(Protocol):
    async def check_chat_history_db(self) -> bool:
        raise NotImplementedError

    async def check_redis(self) -> bool:
        raise NotImplementedError

    async def check_kafka(self) -> bool:
        raise NotImplementedError

