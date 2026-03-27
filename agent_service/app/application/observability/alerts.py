from __future__ import annotations

import logging

from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id


class AlertingMetricsRecorder(MetricsRecorder):
    def __init__(
        self,
        *,
        inner: MetricsRecorder,
        logger: logging.Logger,
        error_count_threshold: int,
        latency_seconds_threshold: float,
        enabled: bool = True,
    ) -> None:
        self._inner = inner
        self._logger = logger
        self._enabled = enabled
        self._error_count_threshold = int(error_count_threshold)
        self._latency_seconds_threshold = float(latency_seconds_threshold)

        self._error_counts: dict[tuple[str, str], int] = {}
        self._error_alerted_keys: set[tuple[str, str]] = set()

    def _key(self, tags: dict[str, str] | None) -> tuple[str, str]:
        component = (tags or {}).get("component", "unknown")
        operation = (tags or {}).get("operation", "unknown")
        return (component, operation)

    def increment(
        self,
        metric_name: str,
        value: int = 1,
        tags: dict[str, str] | None = None,
    ) -> None:
        self._inner.increment(metric_name, value=value, tags=tags)
        if not self._enabled:
            return

        if metric_name != "error_count_total":
            return

        key = self._key(tags)
        self._error_counts[key] = self._error_counts.get(key, 0) + int(value)

        if self._error_counts[key] >= self._error_count_threshold and key not in self._error_alerted_keys:
            self._error_alerted_keys.add(key)
            trace_id = get_trace_id() or "unknown"
            self._logger.warning(
                "alerts.error_count threshold_hit trace_id=%s component=%s operation=%s count=%s threshold=%s tags=%s",
                trace_id,
                key[0],
                key[1],
                self._error_counts[key],
                self._error_count_threshold,
                tags,
            )

    def record_duration_seconds(
        self,
        metric_name: str,
        duration_seconds: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        self._inner.record_duration_seconds(metric_name, duration_seconds=duration_seconds, tags=tags)
        if not self._enabled:
            return

        if metric_name != "latency_seconds":
            return

        if duration_seconds <= self._latency_seconds_threshold:
            return

        trace_id = get_trace_id() or "unknown"
        component, operation = self._key(tags)
        self._logger.warning(
            "alerts.latency threshold_hit trace_id=%s component=%s operation=%s latency_seconds=%.3f threshold=%.3f tags=%s",
            trace_id,
            component,
            operation,
            float(duration_seconds),
            self._latency_seconds_threshold,
            tags,
        )
