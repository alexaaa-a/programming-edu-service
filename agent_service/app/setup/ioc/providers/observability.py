import logging
import os

from dishka import Provider, Scope, provide

from agent_service.app.application.observability.llm_trace import LlmTracer
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.config import Settings
from agent_service.app.infrastructure.observability.langfuse_tracer import build_llm_tracer
from agent_service.app.infrastructure.observability.logging_metrics_recorder import LoggingMetricsRecorder
from agent_service.app.application.observability.alerts import AlertingMetricsRecorder


class MetricsRecorderProvider(Provider):
    @provide(scope=Scope.APP)
    def metrics_recorder(self, logger: logging.Logger) -> MetricsRecorder:
        backend = os.environ.get("METRICS_BACKEND", "").strip().lower()
        alerts_enabled = os.environ.get("ALERTS_ENABLED", "true").strip().lower() in {"1", "true", "yes"}
        error_count_threshold = float(os.environ.get("ALERT_ERROR_COUNT_THRESHOLD", "5"))
        latency_seconds_threshold = float(os.environ.get("ALERT_LATENCY_SECONDS_THRESHOLD", "2.0"))
        if backend == "prometheus":
            from agent_service.app.infrastructure.observability.prometheus_metrics_recorder import (
                PrometheusMetricsRecorder,
            )

            inner = PrometheusMetricsRecorder()
        else:
            inner = LoggingMetricsRecorder(logger=logger)

        return AlertingMetricsRecorder(
            inner=inner,
            logger=logger,
            error_count_threshold=error_count_threshold,
            latency_seconds_threshold=latency_seconds_threshold,
            enabled=alerts_enabled,
        )


class LlmTracerProvider(Provider):
    @provide(scope=Scope.APP)
    def llm_tracer(self, settings: Settings, logger: logging.Logger) -> LlmTracer:
        return build_llm_tracer(settings.langfuse_settings, logger)


ObservabilityProviders = [MetricsRecorderProvider(), LlmTracerProvider()]
