import logging
from collections.abc import AsyncIterable

import httpx
from dishka import Provider, Scope, provide

from agent_service.app.application.interfaces import DecisionModelInterface
from agent_service.app.application.observability.llm_trace import LlmTracer
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.config import Settings
from agent_service.app.infrastructure.decisions import DisabledDecisionModel, JevDecisionModel


class DecisionsHttpProvider(Provider):
    @provide(scope=Scope.APP)
    async def decisions_http_client(self, settings: Settings) -> AsyncIterable[httpx.AsyncClient]:
        timeout = httpx.Timeout(settings.jev_settings.timeout_sec)
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client


class DecisionModelProvider(Provider):
    @provide(scope=Scope.APP, provides=DecisionModelInterface)
    def decision_model(
            self,
            settings: Settings,
            decisions_http_client: httpx.AsyncClient,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
            tracer: LlmTracer,
    ) -> DecisionModelInterface:
        if not settings.jev_settings.is_enabled:
            logger.info("decisions.disabled reason=no_key_or_disabled")
            return DisabledDecisionModel()
        logger.info(
            "decisions.enabled model=%s min_confidence=%.2f",
            settings.jev_settings.model,
            settings.jev_settings.min_confidence,
        )
        return JevDecisionModel(
            client=decisions_http_client,
            settings=settings.jev_settings,
            logger=logger,
            metrics=metrics_recorder,
            tracer=tracer,
        )


DecisionProviders = [DecisionsHttpProvider(), DecisionModelProvider()]
