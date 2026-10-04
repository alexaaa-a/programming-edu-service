from collections.abc import AsyncIterable
import logging

import httpx
import redis.asyncio as redis
from dishka import Provider, Scope, provide
from openai import AsyncOpenAI

from agent_service.app.application.interfaces.trajectory_gateway import (
    TrajectoryGatewayInterface,
)
from agent_service.app.config import Settings
from agent_service.app.application.use_cases.run_drill import RunDrillUseCase
from agent_service.app.application.use_cases.run_task_tests import RunTaskTestsUseCase
from agent_service.app.infrastructure.http import HttpTaskTestsGateway, HttpTrajectoryGateway
from agent_service.app.infrastructure.run_guard import RedisRunGuard


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

    @provide(scope=Scope.APP)
    def task_tests_gateway(
            self,
            settings: Settings,
            submission_http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> HttpTaskTestsGateway:
        return HttpTaskTestsGateway(settings, submission_http_client, logger)

    @provide(scope=Scope.REQUEST)
    def run_task_tests_use_case(
            self,
            task_tests_gateway: HttpTaskTestsGateway,
            redis_client: redis.Redis,
            logger: logging.Logger,
    ) -> RunTaskTestsUseCase:
        return RunTaskTestsUseCase(
            gateway=task_tests_gateway,
            guard=RedisRunGuard(redis_client, logger=logger),
            logger=logger,
        )

    @provide(scope=Scope.REQUEST)
    def run_drill_use_case(
            self,
            task_tests_gateway: HttpTaskTestsGateway,
            redis_client: redis.Redis,
            logger: logging.Logger,
    ) -> RunDrillUseCase:
        return RunDrillUseCase(
            gateway=task_tests_gateway,
            guard=RedisRunGuard(redis_client, logger=logger),
            logger=logger,
        )


HttpProviders = [OpenAIClientSessionProvider(), SubmissionHttpProvider()]
