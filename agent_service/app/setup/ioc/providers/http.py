from collections.abc import AsyncIterable
import logging

import httpx
from dishka import Provider, Scope, provide
from openai import AsyncOpenAI

from agent_service.app.application.interfaces.trajectory_gateway import (
    TrajectoryGatewayInterface,
)
from agent_service.app.config import Settings
from agent_service.app.infrastructure.http import HttpTrajectoryGateway


class OpenAIClientSessionProvider(Provider):
    @provide(scope=Scope.APP)
    async def openai_client(self, settings: Settings) -> AsyncIterable[AsyncOpenAI]:
        llm = settings.openai_settings
        client = AsyncOpenAI(
            api_key=llm.api_key,
            base_url=llm.base_url.rstrip("/"),
            timeout=llm.timeout_sec,
        )
        try:
            yield client
        finally:
            await client.close()


class SubmissionHttpProvider(Provider):
    @provide(scope=Scope.APP)
    async def submission_http_client(self, settings: Settings) -> AsyncIterable[httpx.AsyncClient]:
        timeout = httpx.Timeout(settings.submission_gateway_settings.timeout_sec)
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client

    @provide(scope=Scope.APP)
    def trajectory_gateway(
            self,
            settings: Settings,
            submission_http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> TrajectoryGatewayInterface:
        return HttpTrajectoryGateway(settings, submission_http_client, logger)


HttpProviders = [OpenAIClientSessionProvider(), SubmissionHttpProvider()]
