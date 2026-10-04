import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Literal

from agent_service.app.application.tools.sandbox import run_files


SOLUTION_FILE = "solution.py"
TESTS_FILE = "test_task.py"
REPORT_FILE = "report.xml"
TIMEOUT_SEC = float(os.environ.get("AGENT_SERVICE_HIDDEN_TESTS_TIMEOUT_SEC", "20"))
MAX_CASES = 40
MESSAGE_LIMIT = 220

HiddenTestStatus = Literal["passed", "failed", "error", "unavailable", "timeout"]


def _enabled() -> bool:
    raw = os.environ.get("AGENT_SERVICE_SANDBOX_RUN_HIDDEN_TESTS", "").strip().lower()
    if raw in {"0", "false", "no"}:
        return False
    return True


@dataclass(frozen=True, slots=True)
class HiddenTestCase:
    name: str
    passed: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class HiddenTestRun:
    status: HiddenTestStatus
    total: int = 0
    passed: int = 0
    failed: int = 0
    cases: list[HiddenTestCase] = field(default_factory=list)
    detail: str = ""

    @property
    def ran(self) -> bool:
        return self.status in {"passed", "failed"}

    @property
    def all_passed(self) -> bool:
        return self.status == "passed" and self.total > 0

    @property
    def ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.passed / self.total

    @property
    def failed_names(self) -> list[str]:
        return [case.name for case in self.cases if not case.passed]

    def summary(self) -> str:
        if self.status == "passed":
            return f"тесты задачи пройдены: {self.passed}/{self.total}"
        if self.status == "failed":
            return f"тесты задачи: {self.passed}/{self.total}, упало {self.failed}"
        if self.status == "timeout":
            return "тесты задачи не уложились в лимит времени"
        if self.status == "unavailable":
            return "тесты задачи не запускались"
        return "тесты задачи не удалось прогнать"


async def run_hidden_tests(code: str, tests: str) -> HiddenTestRun:
    if not (tests or "").strip() or not (code or "").strip():
        return HiddenTestRun(status="unavailable", detail="нет тестов или кода")
    if not _enabled():
        return HiddenTestRun(
            status="unavailable",
            detail="прогон выключен (AGENT_SERVICE_SANDBOX_RUN_HIDDEN_TESTS)",
        )
    argv = _pytest_argv()
    if argv is None:
        return HiddenTestRun(status="unavailable", detail="pytest недоступен в окружении")

    try:
        finding, returncode, report = await run_files(
            files={SOLUTION_FILE: code, TESTS_FILE: tests},
            argv=argv,
            timeout=TIMEOUT_SEC,
            tool="hidden_tests",
            fail_prefix="Тесты задачи",
            collect=REPORT_FILE,
        )
    except Exception as e:
        return HiddenTestRun(status="error", detail=f"песочница недоступна: {type(e).__name__}")

    if report:
        parsed = parse_junit(report)
        if parsed is not None:
            return parsed
    if returncode is None and finding is not None and "лимит" in finding.message:
        return HiddenTestRun(status="timeout", detail=finding.message)
    detail = finding.message if finding is not None else "pytest не оставил отчёт"
    if returncode == 5:
        return HiddenTestRun(status="error", detail="в тестах задачи нет ни одного теста")
    return HiddenTestRun(status="error", detail=detail)


def parse_junit(xml_text: str) -> HiddenTestRun | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    cases: list[HiddenTestCase] = []
    for suite in suites:
        for case in suite.iter("testcase"):
            name = str(case.get("name") or "").strip() or "тест"
            problem = None
            for kind in ("failure", "error"):
                node = case.find(kind)
                if node is not None:
                    problem = node
                    break
            if case.find("skipped") is not None and problem is None:
                continue
            message = ""
            if problem is not None:
                message = _clean(problem.get("message") or (problem.text or ""))
                if problem.tag == "error" and "collection" in message.lower():
                    return HiddenTestRun(
                        status="error",
                        detail=_import_error(problem.text or "") or "решение не импортируется",
                    )
            cases.append(
                HiddenTestCase(name=name, passed=problem is None, message=message)
            )
    if not cases:
        return None
    passed = sum(1 for case in cases if case.passed)
    failed = len(cases) - passed
    return HiddenTestRun(
        status="passed" if failed == 0 else "failed",
        total=len(cases),
        passed=passed,
        failed=failed,
        cases=cases[:MAX_CASES],
    )


def _pytest_argv() -> list[str] | None:
    try:
        import pytest  # noqa: F401
    except ImportError:
        return None
    return [
        sys.executable,
        "-m",
        "pytest",
        TESTS_FILE,
        "-q",
        "--tb=no",
        "-p",
        "no:cacheprovider",
        f"--junitxml={REPORT_FILE}",
    ]


def _import_error(traceback: str) -> str:
    lines = [line.strip() for line in (traceback or "").splitlines() if line.strip()]
    for line in reversed(lines):
        body = line.lstrip("E").strip()
        if "Error" in body:
            body = re.sub(r"\(/[^)]*\)", "", body).strip()
            return _clean(f"решение не импортируется: {body}")
    return ""


def _clean(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= MESSAGE_LIMIT:
        return cleaned
    return cleaned[: MESSAGE_LIMIT - 1] + "…"
