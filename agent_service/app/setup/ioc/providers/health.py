from dishka import Provider, Scope, provide
import redis.asyncio as redis

from agent_service.app.config import Settings
from agent_service.app.application.interfaces import HealthDependenciesChecker
from agent_service.app.application.use_cases.well_known.health_check import HealthCheckUseCase
from agent_service.app.infrastructure.health import DependenciesHealthChecker


class HealthDependenciesCheckerProvider(Provider):
    @provide(scope=Scope.APP, provides=HealthDependenciesChecker)
    def health_dependencies_checker(
        self,
        settings: Settings,
        redis_client: redis.Redis,
        kafka_bootstrap_servers: list[str],
    ) -> HealthDependenciesChecker:
        return DependenciesHealthChecker(
            chat_history_db_path=settings.tinydb_settings.chat_history_path,
            redis_client=redis_client,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
        )


class HealthCheckUseCaseProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def health_check_use_case(
        self,
        dependencies_checker: HealthDependenciesChecker,
    ) -> HealthCheckUseCase:
        return HealthCheckUseCase(dependencies_checker=dependencies_checker)


HealthProviders = [HealthDependenciesCheckerProvider(), HealthCheckUseCaseProvider()]

