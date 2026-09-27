from agent_service.app.application.interfaces import HealthDependenciesChecker


class HealthCheckUseCase:
    def __init__(
            self,
            dependencies_checker: HealthDependenciesChecker,
    ) -> None:
        self._dependencies_checker = dependencies_checker

    async def __call__(self) -> None:
        chat_db_ok = await self._dependencies_checker.check_chat_history_db()
        redis_ok = await self._dependencies_checker.check_redis()
        kafka_ok = await self._dependencies_checker.check_kafka()

        if not (chat_db_ok and redis_ok and kafka_ok):
            raise RuntimeError("Not all dependencies are ready")
