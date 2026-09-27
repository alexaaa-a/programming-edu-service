import logging
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from agent_service.app.application.observability.llm_trace import (
    LlmTracer,
    Observation,
    clip_for_trace,
    safe_metadata,
)
from agent_service.app.config import LangfuseSettings


class _LangfuseObservation(Observation):
    def __init__(self, inner: Any, logger: logging.Logger) -> None:
        self._inner = inner
        self._logger = logger

    def update(
            self,
            input: Any = None,
            output: Any = None,
            metadata: Mapping[str, Any] | None = None,
            model: str | None = None,
            model_parameters: Mapping[str, Any] | None = None,
            usage_details: Mapping[str, Any] | None = None,
            level: str | None = None,
            status_message: str | None = None,
            **kwargs: Any,
    ) -> None:
        payload: dict[str, Any] = dict(kwargs)
        if input is not None:
            payload["input"] = clip_for_trace(input)
        if output is not None:
            payload["output"] = clip_for_trace(output)
        if metadata:
            payload["metadata"] = safe_metadata(metadata)
        if model:
            payload["model"] = model
        if model_parameters:
            payload["model_parameters"] = dict(model_parameters)
        if usage_details:
            payload["usage_details"] = dict(usage_details)
        if level:
            payload["level"] = level
        if status_message:
            payload["status_message"] = status_message
        if not payload:
            return
        try:
            self._inner.update(**payload)
        except Exception:
            self._logger.debug("langfuse.observation.update_failed", exc_info=True)

    def update_trace(
            self,
            name: str | None = None,
            user_id: str | None = None,
            session_id: str | None = None,
            tags: Sequence[str] | None = None,
            metadata: Mapping[str, Any] | None = None,
            input: Any = None,
            output: Any = None,
            **kwargs: Any,
    ) -> None:
        payload: dict[str, Any] = dict(kwargs)
        if name:
            payload["name"] = name
        if user_id:
            payload["user_id"] = str(user_id)
        if session_id:
            payload["session_id"] = str(session_id)
        if tags:
            payload["tags"] = [str(tag) for tag in tags if tag]
        if metadata:
            payload["metadata"] = safe_metadata(metadata)
        if input is not None:
            payload["input"] = clip_for_trace(input)
        if output is not None:
            payload["output"] = clip_for_trace(output)
        if not payload:
            return
        try:
            updater = getattr(self._inner, "update_trace", None)
            if updater is None:
                return
            updater(**payload)
        except Exception:
            self._logger.debug("langfuse.trace.update_failed", exc_info=True)

    def score(
            self,
            name: str,
            value: float | int | bool,
            data_type: str = "NUMERIC",
            comment: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"name": name, "value": value, "data_type": data_type}
        if comment:
            payload["comment"] = comment
        try:
            scorer = getattr(self._inner, "score", None)
            if scorer is not None:
                scorer(**payload)
                return
            trace_scorer = getattr(self._inner, "score_trace", None)
            if trace_scorer is not None:
                trace_scorer(**payload)
        except Exception:
            self._logger.debug("langfuse.score.failed name=%s", name, exc_info=True)


class LangfuseLlmTracer(LlmTracer):
    enabled = True

    def __init__(self, settings: LangfuseSettings, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("agent_service")
        self._client = _build_client(settings, self._logger)

    @contextmanager
    def observation(
            self,
            name: str,
            as_type: str = "span",
            input: Any = None,
            output: Any = None,
            metadata: Mapping[str, Any] | None = None,
            user_id: str | None = None,
            session_id: str | None = None,
            tags: Sequence[str] | None = None,
            model: str | None = None,
            model_parameters: Mapping[str, Any] | None = None,
            **kwargs: Any,
    ) -> Iterator[Observation]:
        if self._client is None:
            yield Observation()
            return

        start_kwargs: dict[str, Any] = {
            "name": name,
            "as_type": as_type or "span",
        }
        if input is not None:
            start_kwargs["input"] = clip_for_trace(input)
        if output is not None:
            start_kwargs["output"] = clip_for_trace(output)
        if metadata:
            start_kwargs["metadata"] = safe_metadata(metadata)
        if model:
            start_kwargs["model"] = model
        if model_parameters:
            start_kwargs["model_parameters"] = dict(model_parameters)
        start_kwargs.update(kwargs)

        manager = None
        try:
            manager = self._client.start_as_current_observation(**start_kwargs)
        except TypeError:
            start_kwargs.pop("as_type", None)
            try:
                manager = self._client.start_as_current_observation(**start_kwargs)
            except Exception:
                self._logger.debug("langfuse.observation.start_failed name=%s", name, exc_info=True)
        except Exception:
            self._logger.debug("langfuse.observation.start_failed name=%s", name, exc_info=True)

        if manager is None:
            yield Observation()
            return

        with manager as inner:
            obs = _LangfuseObservation(inner, self._logger)
            obs.update_trace(
                user_id=user_id,
                session_id=session_id,
                tags=tags,
                metadata=metadata,
            )
            try:
                yield obs
            except Exception as exc:
                obs.update(level="ERROR", status_message=str(exc)[:500])
                raise

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception:
            self._logger.debug("langfuse.flush_failed", exc_info=True)

    def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            shutdown = getattr(self._client, "shutdown", None)
            if shutdown is not None:
                shutdown()
            else:
                self._client.flush()
        except Exception:
            self._logger.debug("langfuse.shutdown_failed", exc_info=True)


def build_llm_tracer(settings: LangfuseSettings, logger: logging.Logger | None = None) -> LlmTracer:
    log = logger or logging.getLogger("agent_service")
    if not settings.is_enabled:
        log.info("langfuse.disabled")
        return LlmTracer()
    try:
        tracer = LangfuseLlmTracer(settings, logger=log)
    except Exception:
        log.exception("langfuse.init_failed; continuing without LLM traces")
        return LlmTracer()
    if tracer._client is None:
        log.warning("langfuse.client_missing; continuing without LLM traces")
        return LlmTracer()
    log.info(
        "langfuse.enabled host=%s environment=%s",
        settings.host,
        settings.environment,
    )
    return tracer


def _build_client(settings: LangfuseSettings, logger: logging.Logger) -> Any | None:
    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning("langfuse.package_missing")
        return None

    kwargs: dict[str, Any] = {
        "public_key": settings.public_key,
        "secret_key": settings.secret_key,
        "tracing_enabled": True,
        "environment": settings.environment or "local",
        "debug": settings.debug,
        "sample_rate": max(0.0, min(settings.sample_rate, 1.0)),
        "blocked_instrumentation_scopes": [
            "opentelemetry.instrumentation.fastapi",
            "opentelemetry.instrumentation.asgi",
            "opentelemetry.instrumentation.httpx",
        ],
    }
    host = (settings.host or "").strip().rstrip("/")
    if host:
        kwargs["base_url"] = host
    try:
        return Langfuse(**kwargs)
    except TypeError:
        kwargs.pop("blocked_instrumentation_scopes", None)
        if "base_url" in kwargs:
            kwargs["host"] = kwargs.pop("base_url")
        try:
            return Langfuse(**kwargs)
        except Exception:
            logger.exception("langfuse.client_init_failed")
            return None
    except Exception:
        logger.exception("langfuse.client_init_failed")
        return None
