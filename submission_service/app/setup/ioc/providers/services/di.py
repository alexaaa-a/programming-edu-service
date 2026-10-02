import logging
from collections.abc import AsyncIterable

import httpx
from dishka import provide, Provider, Scope

from submission_service.app.application.interfaces.decisions import DecisionModelInterface
from submission_service.app.application.interfaces.services.token_service import TokenServiceInterface
from submission_service.app.config import Settings
from submission_service.app.infrastructure.decisions import (
    DisabledDecisionModel,
    JevDecisionModel,
)
from submission_service.app.infrastructure.token_service.gateway import TokenService


class ServiceProvider(Provider):
    token_service = provide(TokenService, provides=TokenServiceInterface, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def decisions_http_client(self, settings: Settings) -> AsyncIterable[httpx.AsyncClient]:
        timeout = httpx.Timeout(settings.jev_settings.timeout_sec)
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client

    @provide(scope=Scope.APP, provides=DecisionModelInterface)
    def decision_model(
            self,
            settings: Settings,
            decisions_http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> DecisionModelInterface:
        if not settings.jev_settings.is_enabled:
            logger.info("decisions.disabled reason=no_key_or_disabled")
            return DisabledDecisionModel()
        logger.info("decisions.enabled model=%s", settings.jev_settings.model)
        return JevDecisionModel(
            client=decisions_http_client,
            settings=settings.jev_settings,
            logger=logger,
        )
