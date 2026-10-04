import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.templates.checks import check_task, check_template
from agent_service.app.application.templates.models import (
    CheckIssue,
    DraftSprint,
    DraftTask,
    DraftTemplate,
    GenerationReport,
    GenerationResult,
    TaskReport,
    TemplateSpec,
)
from agent_service.app.application.templates.parsing import (
    extract_json,
    sprint_from_payload,
    task_from_payload,
)
from agent_service.app.application.templates.prompts import (
    SYSTEM_PROMPT,
    repair_prompt,
    sprint_prompt,
)
from agent_service.app.application.tools.hidden_tests import HiddenTestRun, run_hidden_tests


TestRunner = Callable[[str, str], Awaitable[HiddenTestRun]]
TEST_ISSUE_PREFIXES = ("tests_", "reference", "broken", "run_")


@dataclass
class _Stats:
    total: int = 0
    passed: int = 0
    broken_failed: int = 0


@dataclass
class SprintResult:
    sprint: DraftSprint | None
    report: GenerationReport
    project_title: str = ""
    project_description: str = ""
    tasks: list[DraftTask] = field(default_factory=list)


class GenerateProjectTemplateUseCase:
    def __init__(
            self,
            llm: LLMInterface,
            logger: logging.Logger,
            runner: TestRunner | None = None,
            max_rounds: int = 1,
    ) -> None:
        self._llm = llm
        self._logger = logger
        self._runner = runner or run_hidden_tests
        self._max_rounds = max(0, int(max_rounds))

    async def __call__(self, spec: TemplateSpec) -> GenerationResult:
        spec = spec.normalized()
        draft = DraftTemplate(
            title=spec.topic,
            description=spec.topic,
            direction=spec.direction,
            level=spec.level,
        )
        report = GenerationReport(tests_ran=spec.with_tests)
        used: list[str] = []
        for order in range(1, spec.sprints + 1):
            result = await self.generate_sprint(spec, order, used)
            report.issues.extend(result.report.issues)
            report.tasks.extend(result.report.tasks)
            report.rounds = max(report.rounds, result.report.rounds)
            if order == 1:
                draft.title = result.project_title or draft.title
                draft.description = result.project_description or draft.description
            if result.sprint is not None:
                draft.sprints.append(result.sprint)
                used.extend(task.title for task in result.sprint.tasks)
        _tidy(draft)
        report.issues.extend(check_template(draft))
        report.ok = bool(draft.all_tasks()) and not report.issues and all(
            task.ok for task in report.tasks
        )
        return GenerationResult(template=draft, report=report)

    async def generate_sprint(
            self,
            spec: TemplateSpec,
            order: int,
            used_titles: list[str] | None = None,
    ) -> SprintResult:
        spec = spec.normalized()
        report = GenerationReport(tests_ran=spec.with_tests)
        prompt = sprint_prompt(spec, order, list(used_titles or []))
        try:
            payload = extract_json(await self._llm.generate(SYSTEM_PROMPT, prompt))
            sprint = sprint_from_payload(payload, order)
        except Exception as e:
            self._logger.warning("template.sprint.failed order=%s error=%s", order, e)
            report.ok = False
            report.issues.append(
                CheckIssue("sprint_failed", f"Спринт {order} собрать не удалось: {e}")
            )
            return SprintResult(sprint=None, report=report)

        kept: list[DraftTask] = []
        for task in sprint.tasks[: spec.tasks_per_sprint]:
            task_report = await self._verify_task(task, spec, report)
            report.tasks.append(task_report)
            if not task_report.dropped:
                kept.append(task)
        sprint.tasks = kept
        report.ok = bool(kept) and all(task.ok for task in report.tasks)
        return SprintResult(
            sprint=sprint if kept else None,
            report=report,
            project_title=_text(payload.get("title")),
            project_description=_text(payload.get("description")),
            tasks=kept,
        )

    async def _verify_task(
            self,
            task: DraftTask,
            spec: TemplateSpec,
            report: GenerationReport,
    ) -> TaskReport:
        result = TaskReport(title=task.title)
        stats = _Stats()
        issues = await self._issues(task, spec, stats)
        rounds = 0
        while issues and rounds < self._max_rounds:
            rounds += 1
            repaired = await self._repair(task, issues)
            if repaired is None:
                break
            task.title = repaired.title or task.title
            task.description = repaired.description or task.description
            task.tests = repaired.tests or task.tests
            task.reference = repaired.reference or task.reference
            task.broken = repaired.broken or task.broken
            result.title = task.title
            stats = _Stats()
            issues = await self._issues(task, spec, stats)
        report.rounds = max(report.rounds, rounds)
        result.attempts = rounds + 1
        result.tests_total = stats.total
        result.reference_passed = stats.passed
        result.broken_failed = stats.broken_failed

        if not issues:
            result.ok = True
            result.tests_kept = bool(task.tests.strip())
            return result

        result.issues = issues
        result.ok = False
        if all(_is_test_issue(issue) for issue in issues):
            task.tests = ""
            result.tests_kept = False
            self._logger.info("template.task.tests_dropped title=%s", task.title)
            return result

        result.dropped = True
        self._logger.info("template.task.dropped title=%s", task.title)
        return result

    async def _issues(
            self,
            task: DraftTask,
            spec: TemplateSpec,
            stats: _Stats,
    ) -> list[CheckIssue]:
        issues = check_task(task, with_tests=spec.with_tests)
        if issues or not spec.with_tests:
            return issues
        return await self._execution_issues(task, stats)

    async def _execution_issues(self, task: DraftTask, stats: _Stats) -> list[CheckIssue]:
        issues: list[CheckIssue] = []
        name = task.title
        reference = await self._run(task.reference, task.tests)
        if reference is None:
            return [CheckIssue("run_unavailable", "Прогон тестов недоступен", name)]
        stats.total = reference.total
        stats.passed = reference.passed
        if not reference.ran:
            return [
                CheckIssue(
                    "run_failed",
                    "Тесты на эталонном решении не прогнались: "
                    f"{reference.detail or reference.summary()}",
                    name,
                )
            ]
        if not reference.all_passed:
            failing = ", ".join(reference.failed_names[:4]) or "без имён"
            issues.append(
                CheckIssue(
                    "reference_failed",
                    f"Эталонное решение не проходит свои тесты "
                    f"({reference.passed}/{reference.total}): {failing}",
                    name,
                )
            )

        if not task.broken.strip():
            issues.append(
                CheckIssue("broken_missing", "Нет решения с ошибкой, тесты не на чем проверить", name)
            )
            return issues
        broken = await self._run(task.broken, task.tests)
        if broken is None:
            return issues
        if broken.ran and broken.failed == 0:
            issues.append(
                CheckIssue(
                    "tests_blind",
                    "Тесты зелёные и на решении с ошибкой: они ничего не проверяют",
                    name,
                )
            )
        elif broken.ran:
            stats.broken_failed = broken.failed
        else:
            stats.broken_failed = max(1, broken.failed)
        return issues

    async def _run(self, code: str, tests: str) -> HiddenTestRun | None:
        try:
            return await self._runner(code, tests)
        except Exception:
            self._logger.exception("template.run.failed")
            return None

    async def _repair(self, task: DraftTask, issues: list[CheckIssue]) -> DraftTask | None:
        try:
            answer = await self._llm.generate(SYSTEM_PROMPT, repair_prompt(task, issues))
            return task_from_payload(extract_json(answer))
        except Exception as e:
            self._logger.warning("template.repair.failed title=%s error=%s", task.title, e)
            return None


def _tidy(draft: DraftTemplate) -> None:
    sprints = [sprint for sprint in draft.sprints if sprint.tasks]
    draft.sprints = [
        DraftSprint(order=index, title=sprint.title, tasks=sprint.tasks)
        for index, sprint in enumerate(sprints, start=1)
    ]


def _is_test_issue(issue: CheckIssue) -> bool:
    return issue.code.startswith(TEST_ISSUE_PREFIXES)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
