import logging

import httpx
from dishka import Provider, Scope, provide

from agent_service.app.application.interfaces.llm import LLMInterface
from agent_service.app.application.use_cases.generate_project_template import (
    GenerateProjectTemplateUseCase,
)
from agent_service.app.config import Settings
from agent_service.app.infrastructure.http import HttpAdminRoleGateway


class TemplateProvider(Provider):
    @provide(scope=Scope.APP)
    def admin_role_gateway(
            self,
            settings: Settings,
            submission_http_client: httpx.AsyncClient,
            logger: logging.Logger,
    ) -> HttpAdminRoleGateway:
        return HttpAdminRoleGateway(settings, submission_http_client, logger)

    @provide(scope=Scope.REQUEST)
    def generate_project_template(
            self,
            llm: LLMInterface,
            settings: Settings,
            logger: logging.Logger,
    ) -> GenerateProjectTemplateUseCase:
        return GenerateProjectTemplateUseCase(
            llm=llm,
            logger=logger,
            max_rounds=settings.template_settings.max_repair_rounds,
        )


TemplateProviders = [TemplateProvider()]
