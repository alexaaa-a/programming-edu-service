import asyncio

from agent_service.app.application.use_cases.run_task_tests import RunTaskTestsUseCase


TESTS = """
from solution import add

def test_add():
    assert add(2, 2) == 4
"""


class _Gateway:
    def __init__(self, tests: str | None = TESTS) -> None:
        self.tests = tests
        self.calls: list[tuple[int, str]] = []

    async def get_task_tests(self, task_id: int, user_id: str) -> str | None:
        self.calls.append((task_id, user_id))
        return self.tests


class _Guard:
    def __init__(self, free: bool = True) -> None:
        self.free = free
        self.acquired = 0
        self.released = 0

    async def acquire(self, user_id: str) -> bool:
        self.acquired += 1
        return self.free

    async def release(self, user_id: str) -> None:
        self.released += 1


def _run(use_case, code: str, task_id: int = 1, user_id: str = "7"):
    return asyncio.run(use_case(task_id=task_id, code=code, user_id=user_id))


def test_running_the_task_tests_returns_the_result():
    guard = _Guard()
    use_case = RunTaskTestsUseCase(gateway=_Gateway(), guard=guard)
    result = _run(use_case, "def add(a, b):\n    return a + b\n")

    assert result.error is None
    assert result.run is not None and result.run.status == "passed"
    assert (guard.acquired, guard.released) == (1, 1)


def test_wrong_solution_comes_back_with_the_failing_test():
    use_case = RunTaskTestsUseCase(gateway=_Gateway(), guard=_Guard())
    result = _run(use_case, "def add(a, b):\n    return a - b\n")

    assert result.run is not None
    assert result.run.status == "failed"
    assert result.run.failed_names == ["test_add"]


def test_task_without_tests_says_so_and_does_not_run_anything():
    gateway = _Gateway(tests=None)
    guard = _Guard()
    result = _run(RunTaskTestsUseCase(gateway=gateway, guard=guard), "def add(a, b): return a + b")

    assert result.error == "no_tests"
    assert guard.acquired == 0


def test_a_second_run_while_one_is_going_is_refused():
    guard = _Guard(free=False)
    result = _run(RunTaskTestsUseCase(gateway=_Gateway(), guard=guard), "def add(a, b): return a + b")

    assert result.error == "busy"
    assert guard.released == 0


def test_empty_and_oversized_code_is_rejected_before_the_sandbox():
    gateway = _Gateway()
    use_case = RunTaskTestsUseCase(gateway=gateway, guard=_Guard(), max_code_chars=50)

    assert _run(use_case, "   ").error == "empty"
    assert _run(use_case, "x = 1\n" * 100).error == "too_long"
    assert gateway.calls == []


def test_non_python_code_is_not_sent_to_pytest():
    gateway = _Gateway()
    result = _run(
        RunTaskTestsUseCase(gateway=gateway, guard=_Guard()),
        "function add(a, b) { return a + b; }\nconst x = 1;\n",
    )
    assert result.error == "unsupported"
    assert gateway.calls == []


def test_the_gateway_is_asked_for_the_right_task_and_user():
    gateway = _Gateway()
    _run(RunTaskTestsUseCase(gateway=gateway, guard=_Guard()), "def add(a, b): return a + b", task_id=104, user_id="42")
    assert gateway.calls == [(104, "42")]
