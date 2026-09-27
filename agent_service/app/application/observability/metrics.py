import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id

T = TypeVar("T")


def _stringify_tags(tags: dict[str, Any] | None) -> dict[str, str]:
    if not tags:
        return {}
    out: dict[str, str] = {}
    for k, v in tags.items():
        if v is None:
            continue
        out[str(k)] = str(v)
    return out


def instrument_async(
        metrics: MetricsRecorder,
        component: str,
        operation: str,
        tags: dict[str, Any] | None = None,
        request_metric_name: str = "request_count_total",
        error_metric_name: str = "error_count_total",
        latency_metric_name: str = "latency_seconds",
        logger: logging.Logger | None = None,
        log_success: bool = False,
        log_error: bool = True,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    base_tags = {
        **_stringify_tags(tags),
        "component": component,
        "operation": operation,
    }

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            metrics.increment(request_metric_name, 1, tags=base_tags)
            started_at = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
            except Exception:
                metrics.increment(error_metric_name, 1, tags=base_tags)
                if logger is not None and log_error:
                    duration = time.perf_counter() - started_at
                    trace_id = get_trace_id() or "unknown"
                    logger.error(
                        "timing.error trace_id=%s component=%s operation=%s duration_seconds=%.3f tags=%s",
                        trace_id,
                        component,
                        operation,
                        duration,
                        base_tags,
                    )
                metrics.record_duration_seconds(
                    latency_metric_name,
                    time.perf_counter() - started_at,
                    tags={**base_tags, "status": "error"},
                )
                raise

            duration = time.perf_counter() - started_at
            if logger is not None and log_success:
                trace_id = get_trace_id() or "unknown"
                logger.info(
                    "timing.success trace_id=%s component=%s operation=%s duration_seconds=%.3f tags=%s",
                    trace_id,
                    component,
                    operation,
                    duration,
                    base_tags,
                )
            metrics.record_duration_seconds(
                latency_metric_name,
                duration,
                tags={**base_tags, "status": "success"},
            )
            return result

        return wrapper

    return decorator
