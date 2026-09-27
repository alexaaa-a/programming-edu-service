from typing import Any
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


class PrometheusMetricsRecorder(MetricsRecorder):
    def __init__(self) -> None:
        try:
            from prometheus_client import Counter, Histogram, REGISTRY  # type: ignore
        except Exception as e:
            raise ImportError(
                "prometheus_client is required for PrometheusMetricsRecorder. "
                "Install it or switch to another MetricsRecorder implementation."
            ) from e

        self._Counter = Counter
        self._Histogram = Histogram
        self._registry = REGISTRY
        self._cache: dict[tuple[str, str], Any] = {}

    def _get_labels(self, tags: dict[str, str] | None) -> tuple[str, ...]:
        if not tags:
            return tuple()
        return tuple(sorted(tags.keys()))

    def _get_or_create(self, metric_name: str, label_keys: tuple[str, ...], kind: str) -> Any:
        key = (kind, metric_name)
        if key in self._cache:
            return self._cache[key]

        try:
            if kind == "counter":
                metric = self._Counter(metric_name, f"{metric_name} counter", label_keys)  # type: ignore[arg-type]
            else:
                metric = self._Histogram(metric_name, f"{metric_name} latency seconds", label_keys)  # type: ignore[arg-type]
        except ValueError as e:
        
            registry_map = getattr(self._registry, "_names_to_collectors", {})
            metric = registry_map.get(metric_name)
            if metric is None:
                raise e

        self._cache[key] = metric
        return metric

    @staticmethod
    def _metric_label_keys(metric: Any) -> tuple[str, ...]:
        raw = getattr(metric, "_labelnames", ())
        return tuple(str(x) for x in raw)

    def _label_values_for_metric(self, metric: Any, tags: dict[str, str] | None) -> list[str]:
        keys = self._metric_label_keys(metric)
        if not keys:
            return []
        src = tags or {}
        return [src.get(k, "") for k in keys]

    def increment(self, metric_name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        label_keys = self._get_labels(tags)
        metric = self._get_or_create(metric_name, label_keys, kind="counter")
        metric_label_keys = self._metric_label_keys(metric)
        if metric_label_keys:
            label_values = self._label_values_for_metric(metric, tags)
            metric.labels(*label_values).inc(value)
        else:
            metric.inc(value)

    def record_duration_seconds(
            self,
            metric_name: str,
            duration_seconds: float,
            tags: dict[str, str] | None = None,
    ) -> None:
        label_keys = self._get_labels(tags)
        metric = self._get_or_create(metric_name, label_keys, kind="histogram")
        metric_label_keys = self._metric_label_keys(metric)
        if metric_label_keys:
            label_values = self._label_values_for_metric(metric, tags)
            metric.labels(*label_values).observe(duration_seconds)
        else:
            metric.observe(duration_seconds)


def render_prometheus_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
