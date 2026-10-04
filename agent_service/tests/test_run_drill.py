import asyncio

from agent_service.app.application.use_cases.run_drill import RunDrillUseCase


TESTS = """
from solution import double


def test_two():
    assert double(2) == 4


def test_zero():
    assert double(0) == 0


def test_negative():
    assert double(-3) == -6
"""

GOOD = "def double(x):\n    return x * 2\n"
BAD = "def double(x):\n    return x + 2\n"


class _Gateway:
    def __init__(self, tests: str | None = TESTS, skill_id: str = "algorithms") -> None:
        self._tests = tests
        self._skill_id = skill_id
        self.reported: list[tuple[str, str, int, int]] = []
        self.report_ok = True

    async def get_drill_tests(self, drill_id: str):
        if self._tests is None:
            return None
        return self._tests, self._skill_id

    async def report_drill_result(self, drill_id, user_id, passed, total):
        self.reported.append((drill_id, user_id, passed, total))
        return self.report_ok


class _Guard:
    def __init__(self, free: bool = True) -> None:
        self.free = free
        self.released = 0

    async def acquire(self, user_id: str) -> bool:
        return self.free

    async def release(self, user_id: str) -> None:
        self.released += 1


def test_a_passed_drill_is_reported_to_the_model():
    gateway = _Gateway()
    result = asyncio.run(RunDrillUseCase(gateway)(drill_id="d1", code=GOOD, user_id="7"))

    assert result.run is not None and result.run.status == "passed"
    assert (result.run.passed, result.run.total) == (3, 3)
    assert result.recorded is True
    assert gateway.reported == [("d1", "7", 3, 3)]
    assert result.skill_id == "algorithms"


def test_a_failed_drill_is_reported_too():
    gateway = _Gateway()
    result = asyncio.run(RunDrillUseCase(gateway)(drill_id="d1", code=BAD, user_id="7"))

    assert result.run is not None and result.run.status == "failed"
    assert gateway.reported[0][2] < gateway.reported[0][3]
    # студент видит, что именно упало
    assert result.run.failed_names


def test_code_that_does_not_import_is_not_counted_as_practice():
    gateway = _Gateway()
    result = asyncio.run(RunDrillUseCase(gateway)(drill_id="d1", code="def double(x)\n", user_id="7"))

    assert result.run is not None and result.run.ran is False
    assert gateway.reported == []
    assert result.recorded is False


def test_an_unknown_drill_stops_before_the_sandbox():
    gateway = _Gateway(tests=None)
    result = asyncio.run(RunDrillUseCase(gateway)(drill_id="nope", code=GOOD, user_id="7"))

    assert result.error == "no_drill" and result.run is None


def test_empty_and_oversized_code_is_refused():
    gateway = _Gateway()
    uc = RunDrillUseCase(gateway, max_code_chars=50)
    assert asyncio.run(uc(drill_id="d1", code="   ", user_id="7")).error == "empty"
    assert asyncio.run(uc(drill_id="d1", code="x = 1\n" * 100, user_id="7")).error == "too_long"
    assert gateway.reported == []


def test_a_busy_student_waits():
    gateway = _Gateway()
    guard = _Guard(free=False)
    result = asyncio.run(RunDrillUseCase(gateway, guard=guard)(drill_id="d1", code=GOOD, user_id="7"))

    assert result.error == "busy"
    assert gateway.reported == []


def test_the_lock_is_released_after_the_run():
    guard = _Guard()
    asyncio.run(RunDrillUseCase(_Gateway(), guard=guard)(drill_id="d1", code=GOOD, user_id="7"))
    assert guard.released == 1


def test_a_run_still_shows_up_when_reporting_fails():
    gateway = _Gateway()
    gateway.report_ok = False
    result = asyncio.run(RunDrillUseCase(gateway)(drill_id="d1", code=GOOD, user_id="7"))

    assert result.run is not None and result.run.status == "passed"
    assert result.recorded is False
