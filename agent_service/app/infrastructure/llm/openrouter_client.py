from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.observability import instrument_async
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id
from agent_service.app.config import OpenRouterSettings


class OpenRouterClient(LLMInterface):
    def __init__(
        self,
        *,
        session: ClientSession,
        settings: OpenRouterSettings,
        logger: logging.Logger,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._logger = logger
        self._metrics = metrics

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        started_at = time.perf_counter()
        trace_id = get_trace_id() or "unknown"
        system_chars = len(system_prompt)
        user_chars = len(user_prompt)

        self._logger.info(
            "llm.call.start trace_id=%s model=%s system_chars=%s user_chars=%s",
            trace_id,
            self._settings.model,
            system_chars,
            user_chars,
        )

        if not self._settings.api_key:
            self._logger.error("llm.call.error model=%s reason=missing_api_key", self._settings.model)
            raise ValueError("OPENROUTER_API_KEY is required")

        url = f"{self._settings.base_url.rstrip('/')}/chat/completions"

        payload: dict[str, Any] = {
            "model": self._settings.model,
            "temperature": self._settings.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }

        read_sec = float(self._settings.timeout_sec)
        timeout = ClientTimeout(total=read_sec + 45.0, connect=30.0, sock_read=read_sec)

        async def _call_llm() -> str:
            retries = max(0, int(self._settings.retry_count))
            backoff = max(0.0, float(self._settings.retry_backoff_sec))
            attempts = retries + 1

            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    async with self._session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                    ) as resp:
                        text = await resp.text()
                        if resp.status >= 400:
                            self._logger.error(
                                "llm.call.error trace_id=%s model=%s reason=http_status status=%s attempt=%s/%s duration_seconds=%.3f",
                                trace_id,
                                self._settings.model,
                                resp.status,
                                attempt,
                                attempts,
                                time.perf_counter() - started_at,
                            )
                            raise RuntimeError(f"OpenRouter HTTP {resp.status}: {text}")

                        data = json.loads(text)
                    break
                except (asyncio.TimeoutError, ClientError, RuntimeError) as e:
                    last_error = e
                    if attempt >= attempts:
                        raise
                    sleep_for = backoff * attempt if backoff > 0 else 0
                    self._logger.warning(
                        "llm.call.retry trace_id=%s model=%s attempt=%s/%s sleep_seconds=%.2f reason=%s",
                        trace_id,
                        self._settings.model,
                        attempt,
                        attempts,
                        sleep_for,
                        e.__class__.__name__,
                    )
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
            else:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("LLM call failed without explicit exception")

            try:
                content = data["choices"][0]["message"]["content"]
                self._logger.info(
                    "llm.call.end trace_id=%s model=%s duration_seconds=%.3f output_chars=%s",
                    trace_id,
                    self._settings.model,
                    time.perf_counter() - started_at,
                    len(content or ""),
                )
                return content
            except Exception:
                self._logger.exception(
                    "llm.call.error trace_id=%s model=%s reason=unexpected_response duration_seconds=%.3f",
                    trace_id,
                    self._settings.model,
                    time.perf_counter() - started_at,
                )
                raise RuntimeError(f"Unexpected OpenRouter response: {data}")

        if self._metrics is not None:
            decorated = instrument_async(
                self._metrics,
                component="llm",
                operation="generate",
                tags={"provider": "openrouter"},
            )(_call_llm)
            return await decorated()

        return await _call_llm()
