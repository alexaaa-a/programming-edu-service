from abc import abstractmethod
from typing import Protocol


class MetricsRecorder(Protocol):
    @abstractmethod
    def increment(self, metric_name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_duration_seconds(
            self,
            metric_name: str,
            duration_seconds: float,
            tags: dict[str, str] | None = None,
    ) -> None:
        raise NotImplementedError
