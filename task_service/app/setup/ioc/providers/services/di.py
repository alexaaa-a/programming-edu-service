from dishka import provide, Provider, Scope

from task_service.app.application.interfaces.services.token_service import TokenServiceInterface
from task_service.app.infrastructure.token_service.gateway import TokenService


class ServiceProvider(Provider):
    token_service = provide(TokenService, provides=TokenServiceInterface, scope=Scope.APP)
