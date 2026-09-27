from collections.abc import AsyncIterable
import logging

import httpx
from dishka import provide, Provider, Scope

from task_service.app.application.interfaces.admin_role_gateway import (
    AdminRoleGatewayInterface,
)
from task_service.app.application.interfaces.career_llm import CareerLlmInterface
from task_service.app.application.interfaces.review_gateway import (
    TaskReviewGatewayInterface,
    TrajectoryGatewayInterface,
)
from task_service.app.application.interfaces.services.token_service import TokenServiceInterface
from task_service.app.config import Settings
from task_service.app.infrastructure.http.admin_role import HttpAdminRoleGateway
from task_service.app.infrastructure.http.career_llm import HttpCareerLlm
from task_service.app.infrastructure.http.submission_reviews import HttpTaskReviewGateway
from task_service.app.infrastructure.token_service.gateway import TokenService


class ServiceProvider(Provider):
    token_service = provide(TokenService, provides=TokenServiceInterface, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def http_client(self, settings: Settings) -> AsyncIterable[httpx.AsyncClient]:
        timeout = httpx.Timeout(
            max(
                settings.submission_gateway_settings.timeout_sec,
                settings.user_gateway_settings.timeout_sec,
            )
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client

    @provide(scope=Scope.APP)
    def submission_gateway(
            self,
            settings: Settings,
            http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> HttpTaskReviewGateway:
        return HttpTaskReviewGateway(settings, http_client, logger)

    @provide(scope=Scope.APP)
    def review_gateway(self, submission_gateway: HttpTaskReviewGateway) -> TaskReviewGatewayInterface:
        return submission_gateway

    @provide(scope=Scope.APP)
    def trajectory_gateway(
            self,
            submission_gateway: HttpTaskReviewGateway,
    ) -> TrajectoryGatewayInterface:
        return submission_gateway

    @provide(scope=Scope.APP)
    def career_llm(
            self,
            settings: Settings,
            http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> CareerLlmInterface:
        return HttpCareerLlm(settings, http_client, logger)

    @provide(scope=Scope.APP)
    def admin_role_gateway(
            self,
            settings: Settings,
            http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> AdminRoleGatewayInterface:
        return HttpAdminRoleGateway(settings, http_client, logger)
