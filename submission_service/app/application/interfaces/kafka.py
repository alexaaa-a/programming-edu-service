from abc import abstractmethod
from typing import Protocol


class SubmissionEventProducerInterface(Protocol):

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def produce_submission_created(
        self,
        *,
        submission_id: int,
        task_id: int,
        user_id: int,
        code: str,
        task_description: str,
    ) -> None:
        raise NotImplementedError
