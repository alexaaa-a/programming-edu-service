import logging
from dataclasses import dataclass
from typing import Protocol

from agent_service.app.application.tools.hidden_tests import HiddenTestRun, run_hidden_tests
from agent_service.app.application.tools.static_analysis import detect_language


@dataclass(frozen=True, slots=True)
class RunDrillResult:
    run: HiddenTestRun | None = None
    skill_id: str = ""
    recorded: bool = False
    error: str | None = None
    message: str | None = None


class DrillsGateway(Protocol):
    async def get_drill_tests(self, drill_id: str) -> tuple[str, str] | None: ...

    async def report_drill_result(
            self,
            drill_id: str,
            user_id: str,
            passed: int,
            total: int,
    ) -> bool: ...


class RunGuard(Protocol):
    async def acquire(self, user_id: str) -> bool: ...

    async def release(self, user_id: str) -> None: ...


class RunDrillUseCase:
    def __init__(
            self,
            gateway: DrillsGateway,
            guard: RunGuard | None = None,
            logger: logging.Logger | None = None,
            max_code_chars: int = 20_000,
    ) -> None:
        self._gateway = gateway
        self._guard = guard
        self._logger = logger or logging.getLogger("agent_service.run_drill")
        self._max_code_chars = max_code_chars

    async def __call__(self, drill_id: str, code: str, user_id: str) -> RunDrillResult:
        if not (code or "").strip():
            return RunDrillResult(error="empty", message="Сначала напиши код.")
        if len(code) > self._max_code_chars:
            return RunDrillResult(error="too_long", message="Для упражнения это слишком много кода.")
        if detect_language(code) != "python":
            return RunDrillResult(error="unsupported", message="Упражнения только на Python.")

        found = await self._gateway.get_drill_tests(drill_id)
        if found is None:
            return RunDrillResult(error="no_drill", message="Упражнение не найдено.")
        tests, skill_id = found

        if self._guard is not None and not await self._guard.acquire(user_id):
            return RunDrillResult(
                error="busy",
                message="Прошлый прогон ещё идёт. Подожди несколько секунд.",
            )
        try:
            run = await run_hidden_tests(code, tests)
        finally:
            if self._guard is not None:
                await self._guard.release(user_id)

        if run.status == "unavailable":
            return RunDrillResult(
                run=run,
                skill_id=skill_id,
                error="unavailable",
                message="Прогон сейчас недоступен.",
            )

        recorded = False
        if run.ran:
            recorded = await self._gateway.report_drill_result(
                drill_id, user_id, run.passed, run.total
            )
        self._logger.info(
            "run_drill.done user_id=%s drill=%s status=%s passed=%s/%s recorded=%s",
            user_id,
            drill_id,
            run.status,
            run.passed,
            run.total,
            recorded,
        )
        return RunDrillResult(run=run, skill_id=skill_id, recorded=recorded)
