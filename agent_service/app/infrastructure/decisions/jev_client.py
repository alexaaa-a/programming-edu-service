import logging
import time
from typing import Any, Mapping, Sequence

import httpx

from agent_service.app.application.decisions.questions import (
    Answers,
    Question,
    parse_answers,
    questions_payload,
)
from agent_service.app.application.interfaces.decisions import DecisionModelInterface
from agent_service.app.application.observability.llm_trace import (
    LlmTracer,
    clip_for_trace,
    get_noop_tracer,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id
from agent_service.app.config import JevSettings


class JevDecisionModel(DecisionModelInterface):
    def __init__(
            self,
            client: httpx.AsyncClient,
            settings: JevSettings,
            logger: logging.Logger | None = None,
            metrics: MetricsRecorder | None = None,
            tracer: LlmTracer | None = None,
            clock: Any = time.monotonic,
    ) -> None:
        self._client = client
        self._settings = settings
        self._logger = logger or logging.getLogger("agent_service.decisions")
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0

    @property
    def enabled(self) -> bool:
        return self._settings.is_enabled

    async def ask(
            self,
            state: str | Mapping[str, Any],
            questions: Sequence[Question],
            label: str = "",
    ) -> Answers:
        if not questions:
            return Answers.unavailable("no_questions")
        if not self.enabled:
            return Answers.unavailable("disabled")
        if self._paused():
            self._record(label, "paused", 0.0, len(questions))
            return Answers.unavailable("cooldown")

        try:
            payload = {
                "model": self._settings.model,
                "state": state,
                "questions": questions_payload(questions),
            }
        except ValueError as e:
            self._logger.error("decisions.build_failed label=%s reason=%s", label, e)
            return Answers.unavailable("bad_questions")

        started = self._clock()
        with self._tracer.observation(
            "decisions.ask",
            as_type="generation",
            model=self._settings.model,
            model_parameters={"timeout_sec": self._settings.timeout_sec},
            input={
                "state": clip_for_trace(_as_text(state), max_chars=2000),
                "questions": [question.name for question in questions],
            },
            metadata={
                "app_trace_id": get_trace_id() or "unknown",
                "provider": "openrouter",
                "label": label,
                "kinds": ",".join(question.kind for question in questions),
            },
        ) as observation:
            try:
                response = await self._client.post(
                    f"{self._settings.base_url.rstrip('/')}/alpha/decisions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._settings.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=self._settings.timeout_sec,
                )
            except Exception as e:
                elapsed = self._elapsed_ms(started)
                self._on_failure()
                observation.update(level="ERROR", status_message=f"transport:{type(e).__name__}")
                self._logger.warning(
                    "decisions.failed label=%s reason=transport error=%s duration_ms=%.1f",
                    label,
                    type(e).__name__,
                    elapsed,
                )
                self._record(label, "transport_error", elapsed, len(questions))
                return Answers.unavailable("transport_error", latency_ms=elapsed)

            elapsed = self._elapsed_ms(started)
            if response.status_code != 200:
                self._on_failure()
                observation.update(level="ERROR", status_message=f"http:{response.status_code}")
                self._logger.warning(
                    "decisions.failed label=%s reason=http status=%s body=%s",
                    label,
                    response.status_code,
                    clip_for_trace(response.text, max_chars=300),
                )
                self._record(label, f"http_{response.status_code}", elapsed, len(questions))
                return Answers.unavailable(f"http_{response.status_code}", latency_ms=elapsed)

            try:
                body = response.json()
            except Exception:
                body = None
            if not isinstance(body, Mapping):
                self._on_failure()
                observation.update(level="ERROR", status_message="bad_body")
                self._record(label, "bad_body", elapsed, len(questions))
                return Answers.unavailable("bad_body", latency_ms=elapsed)

            answers = parse_answers(body, questions, latency_ms=elapsed)
            if not answers:
                self._on_failure()
                observation.update(level="WARNING", status_message=answers.reason)
                self._record(label, answers.reason or "empty", elapsed, len(questions))
                return answers

            self._failures = 0
            observation.update(
                output={name: _answer_for_trace(value) for name, value in answers.items.items()},
                usage_details=_usage_details(body.get("usage")),
                metadata={"latency_ms": round(elapsed, 1), "model": answers.model},
            )
            self._logger.info(
                "decisions.ok label=%s questions=%s duration_ms=%.1f model=%s",
                label,
                ",".join(question.name for question in questions),
                elapsed,
                answers.model or self._settings.model,
            )
            self._record(label, "ok", elapsed, len(questions))
            return answers

    def _paused(self) -> bool:
        return self._failures >= self._settings.failure_threshold and self._clock() < self._open_until

    def _on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._settings.failure_threshold:
            self._open_until = self._clock() + self._settings.cooldown_sec
            self._logger.warning(
                "decisions.cooldown failures=%s seconds=%.0f",
                self._failures,
                self._settings.cooldown_sec,
            )

    def _elapsed_ms(self, started: float) -> float:
        return (self._clock() - started) * 1000.0

    def _record(self, label: str, outcome: str, latency_ms: float, questions: int) -> None:
        if self._metrics is None:
            return
        tags = {"label": label or "unknown", "outcome": outcome}
        self._metrics.increment("decisions_requests_total", 1, tags=tags)
        self._metrics.increment("decisions_questions_total", questions, tags=tags)
        self._metrics.record_duration_seconds(
            "decisions_duration_seconds",
            latency_ms / 1000.0,
            tags={"label": label or "unknown"},
        )


class DisabledDecisionModel(DecisionModelInterface):
    @property
    def enabled(self) -> bool:
        return False

    async def ask(
            self,
            state: str | Mapping[str, Any],
            questions: Sequence[Question],
            label: str = "",
    ) -> Answers:
        return Answers.unavailable("disabled")


def _as_text(state: str | Mapping[str, Any]) -> str:
    if isinstance(state, str):
        return state
    import json

    try:
        return json.dumps(state, ensure_ascii=False)
    except Exception:
        return str(state)


def _answer_for_trace(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    confidence = getattr(value, "confidence", None)
    payload: dict[str, Any] = {}
    if hasattr(value, "value"):
        raw = value.value
        payload["value"] = round(raw, 3) if isinstance(raw, float) else raw
    if confidence is not None:
        payload["confidence"] = round(float(confidence), 3)
    return payload or str(value)


def _usage_details(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, Mapping):
        return None
    details: dict[str, int] = {}
    for source, target in (
        ("input_tokens", "input"),
        ("output_tokens", "output"),
        ("prompt_tokens", "input"),
        ("completion_tokens", "output"),
    ):
        raw = usage.get(source)
        if isinstance(raw, (int, float)):
            details[target] = int(raw)
    if details:
        details["total"] = details.get("input", 0) + details.get("output", 0)
    return details or None
