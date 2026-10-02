import logging
import time
from typing import Any, Mapping, Sequence

import httpx

from submission_service.app.application.decisions.questions import (
    Answers,
    Question,
    parse_answers,
    questions_payload,
)
from submission_service.app.application.interfaces.decisions import DecisionModelInterface
from submission_service.app.config import JevSettings


class JevDecisionModel(DecisionModelInterface):
    def __init__(
            self,
            client: httpx.AsyncClient,
            settings: JevSettings,
            logger: logging.Logger | None = None,
            clock: Any = time.monotonic,
    ) -> None:
        self._client = client
        self._settings = settings
        self._logger = logger or logging.getLogger("submission_service.decisions")
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
            self._on_failure()
            self._logger.warning(
                "decisions.failed label=%s reason=transport error=%s", label, type(e).__name__
            )
            return Answers.unavailable("transport_error", latency_ms=self._elapsed_ms(started))

        elapsed = self._elapsed_ms(started)
        if response.status_code != 200:
            self._on_failure()
            self._logger.warning(
                "decisions.failed label=%s reason=http status=%s", label, response.status_code
            )
            return Answers.unavailable(f"http_{response.status_code}", latency_ms=elapsed)

        try:
            body = response.json()
        except Exception:
            body = None
        if not isinstance(body, Mapping):
            self._on_failure()
            return Answers.unavailable("bad_body", latency_ms=elapsed)

        answers = parse_answers(body, questions, latency_ms=elapsed)
        if not answers:
            self._on_failure()
            return answers
        self._failures = 0
        self._logger.info(
            "decisions.ok label=%s questions=%s duration_ms=%.1f",
            label,
            len(questions),
            elapsed,
        )
        return answers

    def _paused(self) -> bool:
        return self._failures >= self._settings.failure_threshold and self._clock() < self._open_until

    def _on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._settings.failure_threshold:
            self._open_until = self._clock() + self._settings.cooldown_sec
            self._logger.warning("decisions.cooldown failures=%s", self._failures)

    def _elapsed_ms(self, started: float) -> float:
        return (self._clock() - started) * 1000.0


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
