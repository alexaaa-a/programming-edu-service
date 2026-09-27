import logging

from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


class LoggingMetricsRecorder(MetricsRecorder):
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def increment(
            self,
            metric_name: str,
            value: int = 1,
            tags: dict[str, str] | None = None,
    ) -> None:
        status = (tags or {}).get("status")
        if status == "error":
            self._logger.error("metrics.increment metric=%s value=%s tags=%s", metric_name, value, tags)

    def record_duration_seconds(
            self,
            metric_name: str,
            duration_seconds: float,
            tags: dict[str, str] | None = None,
    ) -> None:
        status = (tags or {}).get("status")
        if status == "error":
            self._logger.error(
                "metrics.duration metric=%s duration_seconds=%.6f tags=%s",
                metric_name,
                duration_seconds,
                tags,
            )
