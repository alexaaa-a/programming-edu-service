from dishka import provide, Provider, Scope

from user_service.app.application.interfaces.register.password_service import PasswordServiceInterface
from user_service.app.application.interfaces.register.token_service import TokenServiceInterface
from user_service.app.infrastructure.authorization.token_service import JWTTokenService
from user_service.app.infrastructure.authorization.password_service import PasswordService


class ServiceProvider(Provider):
    token_service = provide(JWTTokenService, provides=TokenServiceInterface, scope=Scope.APP)
    password_service = provide(PasswordService, provides=PasswordServiceInterface, scope=Scope.APP)
