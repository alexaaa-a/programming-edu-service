import logging
from dataclasses import replace

from agent_service.app.application.interfaces import (
    GraphMemoryInterface,
    MemoryInterface,
    StudentProfileRepository,
)
from agent_service.app.application.tools.graph_facts import load_graph_facts
from agent_service.app.application.tools.models import ToolFinding, ToolReport
from agent_service.app.application.tools.past_reviews import (
    load_past_reviews,
    load_student_notes,
    score_cap_from_report,
)
from agent_service.app.application.tools.hidden_tests import HiddenTestRun, run_hidden_tests
from agent_service.app.application.tools.sandbox import compile_javascript, compile_python, run_python_tests
from agent_service.app.application.tools.static_analysis import analyze_code, detect_language


class ReviewToolkit:
    def __init__(
            self,
            memory: MemoryInterface,
            logger: logging.Logger | None = None,
            profiles: StudentProfileRepository | None = None,
            graph: GraphMemoryInterface | None = None,
    ) -> None:
        self._memory = memory
        self._profiles = profiles
        self._graph = graph
        self._logger = logger or logging.getLogger("agent_service")

    async def inspect(
            self,
            code: str,
            task_description: str,
            task_id: str | None = None,
            user_id: str | None = None,
            hidden_tests: str | None = None,
    ) -> ToolReport:
        language = detect_language(code)
        findings: list[ToolFinding] = []

        syntax_ok, static_findings = analyze_code(code, language)
        findings.extend(static_findings)

        compile_ok = syntax_ok
        if syntax_ok and language == "python":
            compile_hit = await compile_python(code)
            if compile_hit is not None:
                compile_ok = False
                findings.append(compile_hit)
        elif syntax_ok and language == "javascript":
            compile_hit = await compile_javascript(code)
            if compile_hit is not None:
                compile_ok = False
                findings.append(compile_hit)

        tests_run = False
        tests_passed: bool | None = None
        if language == "python" and compile_ok:
            tests_passed, test_hit = await run_python_tests(code)
            tests_run = tests_passed is not None
            if test_hit is not None:
                findings.append(test_hit)

        hidden: HiddenTestRun | None = None
        if language == "python" and (hidden_tests or "").strip():
            hidden = await run_hidden_tests(code, hidden_tests or "")
            findings.extend(_hidden_findings(hidden))

        try:
            past = await load_past_reviews(
                self._memory,
                task_description=task_description,
                task_id=task_id,
                user_id=user_id,
            )
            findings.extend(past)
            findings.extend(await self._student_context(task_description, task_id, user_id))
        except Exception:
            self._logger.exception("tools.past_reviews.failed")

        report = ToolReport(
            language=language,
            findings=findings,
            syntax_ok=syntax_ok,
            compile_ok=compile_ok,
            tests_run=tests_run,
            tests_passed=tests_passed,
            hidden=hidden,
        )
        report = replace(report, score_cap=score_cap_from_report(report))
        self._logger.info(
            "tools.inspect language=%s syntax_ok=%s compile_ok=%s tests_run=%s tests_passed=%s cap=%s findings=%s "
            "hidden=%s",
            report.language,
            report.syntax_ok,
            report.compile_ok,
            report.tests_run,
            report.tests_passed,
            report.score_cap,
            len(report.findings),
            hidden.summary() if hidden is not None else "нет",
        )
        return report


    async def _student_context(
            self,
            task_description: str,
            task_id: str | None,
            user_id: str | None,
    ) -> list[ToolFinding]:
        graph_facts = await load_graph_facts(
            self._graph,
            user_id=user_id,
            task_description=task_description,
            task_id=task_id,
            logger=self._logger,
        )
        if graph_facts:
            return graph_facts
        return await load_student_notes(self._profiles, user_id=user_id)


def _hidden_findings(run: HiddenTestRun) -> list[ToolFinding]:
    if run.status == "passed":
        return [ToolFinding("hidden_tests", "info", f"Тесты задачи пройдены: {run.passed}/{run.total}")]
    if run.status == "failed":
        names = ", ".join(run.failed_names[:4])
        message = f"Тесты задачи: {run.passed}/{run.total}. Упали: {names or 'без имён'}"
        return [ToolFinding("hidden_tests", "error", message)]
    if run.status in {"error", "timeout"}:
        return [ToolFinding("hidden_tests", "error", f"Тесты задачи не прогнались: {run.detail or run.status}")]
    return []
