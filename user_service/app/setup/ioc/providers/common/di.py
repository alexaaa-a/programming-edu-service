import logging
from dishka import Provider, Scope, from_context, provide

from user_service.app.config import Settings


class SettingsProvider(Provider):
    scope = Scope.APP

    settings = from_context(Settings)


class LoggingProvider(Provider):

    @provide(scope=Scope.APP)
    def logger(self) -> logging.Logger:
        return logging.getLogger(__name__)
