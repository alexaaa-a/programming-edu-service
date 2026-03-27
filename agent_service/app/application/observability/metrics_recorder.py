from typing import Protocol


class MetricsRecorder(Protocol):
    def increment(self, metric_name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:  # noqa: E501
        raise NotImplementedError

    def record_duration_seconds(
        self,
        metric_name: str,
        duration_seconds: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        raise NotImplementedError
