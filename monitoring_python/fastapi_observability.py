import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def configure_observability(app: FastAPI, *, service_name: str) -> None:
    _configure_prometheus(app)
    _configure_otel(app, service_name=service_name)


def _configure_prometheus(app: FastAPI) -> None:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    except ImportError:
        logger.warning("prometheus_fastapi_instrumentator not installed; /metrics disabled")


def _configure_otel(app: FastAPI, *, service_name: str) -> None:
    if os.getenv("OTEL_SDK_DISABLED", "").lower() in ("1", "true", "yes"):
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning("OpenTelemetry packages not installed; tracing disabled")
        return

    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in ("1", "true", "yes")

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": os.getenv("OTEL_ENVIRONMENT", "development"),
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
