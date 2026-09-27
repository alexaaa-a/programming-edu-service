import logging
import time
from typing import Any

from openai import APIError, AsyncOpenAI, APITimeoutError

from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.observability import instrument_async
from agent_service.app.application.observability.llm_trace import LlmTracer, clip_for_trace, get_noop_tracer
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id
from agent_service.app.config import OpenAISettings


class OpenAIClient(LLMInterface):
    def __init__(
            self,
            client: AsyncOpenAI,
            settings: OpenAISettings,
            logger: logging.Logger,
            metrics: MetricsRecorder | None = None,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._logger = logger
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        started_at = time.perf_counter()
        trace_id = get_trace_id() or "unknown"
        model = self._settings.model

        self._logger.info(
            "llm.call.start trace_id=%s model=%s system_chars=%s user_chars=%s",
            trace_id,
            model,
            len(system_prompt),
            len(user_prompt),
        )

        if not self._settings.api_key:
            self._logger.error("llm.call.error model=%s reason=missing_api_key", model)
            raise ValueError("AGENT_SERVICE_OPENAI_API_KEY is required")

        async def _call_llm() -> str:
            with self._tracer.observation(
                "llm.generate",
                as_type="generation",
                model=model,
                model_parameters={
                    "reasoning_effort": self._settings.reasoning_effort,
                    "timeout_sec": self._settings.timeout_sec,
                    **(
                        {"temperature": self._settings.temperature}
                        if self._settings.reasoning_effort == "none"
                        else {}
                    ),
                },
                input={
                    "messages": [
                        {"role": "system", "content": clip_for_trace(system_prompt, max_chars=2500)},
                        {"role": "user", "content": clip_for_trace(user_prompt, max_chars=3500)},
                    ]
                },
                metadata={
                    "app_trace_id": trace_id,
                    "provider": "openai",
                    "system_chars": len(system_prompt),
                    "user_chars": len(user_prompt),
                },
            ) as generation:
                try:
                    response = await self._client.chat.completions.create(
                        **_completion_kwargs(
                            model=model,
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            temperature=self._settings.temperature,
                            reasoning_effort=self._settings.reasoning_effort,
                        )
                    )
                except APITimeoutError as e:
                    generation.update(level="ERROR", status_message="timeout")
                    self._logger.error(
                        "llm.call.error trace_id=%s model=%s reason=timeout duration_seconds=%.3f",
                        trace_id,
                        model,
                        time.perf_counter() - started_at,
                    )
                    raise RuntimeError("OpenAI request timed out") from e
                except APIError as e:
                    generation.update(
                        level="ERROR",
                        status_message=f"api_error:{getattr(e, 'status_code', None)}",
                    )
                    self._logger.error(
                        "llm.call.error trace_id=%s model=%s reason=api_error status=%s duration_seconds=%.3f",
                        trace_id,
                        model,
                        getattr(e, "status_code", None),
                        time.perf_counter() - started_at,
                    )
                    raise RuntimeError(f"OpenAI API error: {e}") from e

                content = response.choices[0].message.content if response.choices else None
                if not content:
                    generation.update(level="ERROR", status_message="empty_response")
                    self._logger.error(
                        "llm.call.error trace_id=%s model=%s reason=empty_response duration_seconds=%.3f",
                        trace_id,
                        model,
                        time.perf_counter() - started_at,
                    )
                    raise RuntimeError("Empty OpenAI chat completion")

                generation.update(
                    output=clip_for_trace(content, max_chars=4000),
                    usage_details=_usage_details(response),
                    metadata={"output_chars": len(content)},
                )
                self._logger.info(
                    "llm.call.end trace_id=%s model=%s duration_seconds=%.3f output_chars=%s",
                    trace_id,
                    model,
                    time.perf_counter() - started_at,
                    len(content),
                )
                return content

        if self._metrics is not None:
            decorated = instrument_async(
                self._metrics,
                component="llm",
                operation="generate",
                tags={"provider": "openai"},
            )(_call_llm)
            return await decorated()

        return await _call_llm()


def _completion_kwargs(
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        reasoning_effort: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if reasoning_effort == "none":
        payload["temperature"] = temperature
    return payload


def _usage_details(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    total = getattr(usage, "total_tokens", None)
    details: dict[str, int] = {}
    if prompt is not None:
        details["input"] = int(prompt)
        details["prompt_tokens"] = int(prompt)
    if completion is not None:
        details["output"] = int(completion)
        details["completion_tokens"] = int(completion)
    if total is not None:
        details["total"] = int(total)
        details["total_tokens"] = int(total)
    return details or None
