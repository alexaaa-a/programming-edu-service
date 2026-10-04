import logging
from dataclasses import dataclass
from typing import Protocol

from agent_service.app.application.tools.hidden_tests import HiddenTestRun, run_hidden_tests
from agent_service.app.application.tools.static_analysis import detect_language


@dataclass(frozen=True, slots=True)
class RunTestsResult:
    run: HiddenTestRun | None = None
    error: str | None = None
    message: str | None = None


class TaskTestsGateway(Protocol):
    async def get_task_tests(
            self,
            task_id: int,
            user_id: str,
    ) -> str | None: ...


class RunGuard(Protocol):
    async def acquire(self, user_id: str) -> bool: ...

    async def release(self, user_id: str) -> None: ...


class RunTaskTestsUseCase:
    def __init__(
            self,
            gateway: TaskTestsGateway,
            guard: RunGuard | None = None,
            logger: logging.Logger | None = None,
            max_code_chars: int = 40_000,
    ) -> None:
        self._gateway = gateway
        self._guard = guard
        self._logger = logger or logging.getLogger("agent_service.run_tests")
        self._max_code_chars = max_code_chars

    async def __call__(self, task_id: int, code: str, user_id: str) -> RunTestsResult:
        if not (code or "").strip():
            return RunTestsResult(error="empty", message="Сначала напиши код.")
        if len(code) > self._max_code_chars:
            return RunTestsResult(error="too_long", message="Код слишком большой для прогона.")
        if detect_language(code) != "python":
            return RunTestsResult(
                error="unsupported",
                message="Тесты задачи запускаются только для Python.",
            )

        tests = await self._gateway.get_task_tests(task_id, user_id)
        if not tests:
            return RunTestsResult(
                error="no_tests",
                message="У этой задачи нет тестов: её проверяет только команда.",
            )

        if self._guard is not None and not await self._guard.acquire(user_id):
            return RunTestsResult(
                error="busy",
                message="Прошлый прогон ещё идёт. Подожди несколько секунд.",
            )
        try:
            run = await run_hidden_tests(code, tests)
        finally:
            if self._guard is not None:
                await self._guard.release(user_id)

        self._logger.info(
            "run_tests.done user_id=%s task_id=%s status=%s passed=%s/%s",
            user_id,
            task_id,
            run.status,
            run.passed,
            run.total,
        )
        if run.status == "unavailable":
            return RunTestsResult(
                run=run,
                error="unavailable",
                message="Прогон тестов сейчас недоступен.",
            )
        return RunTestsResult(run=run)
