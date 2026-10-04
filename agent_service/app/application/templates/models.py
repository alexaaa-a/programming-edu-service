from dataclasses import dataclass, field
from typing import Any


RESERVED_TITLES = frozenset({"Ночной инцидент", "Ревью стажёра"})


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    topic: str
    direction: str = "backend"
    level: str = "junior"
    sprints: int = 3
    tasks_per_sprint: int = 4
    notes: str = ""
    with_tests: bool = True

    def normalized(self) -> "TemplateSpec":
        return TemplateSpec(
            topic=" ".join(self.topic.split())[:200],
            direction=(self.direction or "backend").strip().lower()[:32],
            level=(self.level or "junior").strip().lower()[:32],
            sprints=max(1, min(int(self.sprints or 1), 5)),
            tasks_per_sprint=max(2, min(int(self.tasks_per_sprint or 2), 6)),
            notes=" ".join((self.notes or "").split())[:600],
            with_tests=bool(self.with_tests),
        )

    @property
    def total_tasks(self) -> int:
        return self.sprints * self.tasks_per_sprint


@dataclass
class DraftTask:
    title: str
    description: str
    tests: str = ""
    reference: str = ""
    broken: str = ""

    def as_template_task(self) -> dict[str, str]:
        return {"title": self.title, "description": self.description, "tests": self.tests}


@dataclass
class DraftSprint:
    order: int
    title: str
    tasks: list[DraftTask] = field(default_factory=list)


@dataclass
class DraftTemplate:
    title: str
    description: str
    direction: str
    level: str
    sprints: list[DraftSprint] = field(default_factory=list)

    def all_tasks(self) -> list[DraftTask]:
        return [task for sprint in self.sprints for task in sprint.tasks]

    def as_template(self) -> dict[str, Any]:
        return {
            "project_template_id": None,
            "title": self.title,
            "description": self.description,
            "direction": self.direction,
            "level": self.level,
            "sprints": [
                {
                    "order": sprint.order,
                    "title": sprint.title,
                    "tasks": [task.as_template_task() for task in sprint.tasks],
                }
                for sprint in self.sprints
            ],
        }


@dataclass(frozen=True, slots=True)
class CheckIssue:
    code: str
    message: str
    task: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "task": self.task}


@dataclass
class TaskReport:
    title: str
    ok: bool = True
    attempts: int = 1
    tests_total: int = 0
    reference_passed: int = 0
    broken_failed: int = 0
    tests_kept: bool = False
    dropped: bool = False
    issues: list[CheckIssue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "ok": self.ok,
            "attempts": self.attempts,
            "tests_total": self.tests_total,
            "reference_passed": self.reference_passed,
            "broken_failed": self.broken_failed,
            "tests_kept": self.tests_kept,
            "dropped": self.dropped,
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass
class GenerationReport:
    ok: bool = True
    rounds: int = 0
    tasks: list[TaskReport] = field(default_factory=list)
    issues: list[CheckIssue] = field(default_factory=list)
    tests_ran: bool = False

    @property
    def with_tests(self) -> int:
        return sum(1 for task in self.tasks if task.tests_kept)

    @property
    def dropped(self) -> list[str]:
        return [task.title for task in self.tasks if task.dropped]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rounds": self.rounds,
            "tests_ran": self.tests_ran,
            "tasks_total": len(self.tasks),
            "tasks_with_tests": self.with_tests,
            "dropped": self.dropped,
            "issues": [issue.as_dict() for issue in self.issues],
            "tasks": [task.as_dict() for task in self.tasks],
        }

    def as_text(self) -> str:
        if not self.tasks:
            return "Ни одной задачи собрать не удалось."
        lines = [
            f"Задач: {len(self.tasks)}, с тестами: {self.with_tests}, "
            f"кругов правок: {self.rounds}."
        ]
        for task in self.tasks:
            if task.dropped:
                lines.append(f"— {task.title}: снята, {_first(task.issues)}")
            elif task.tests_kept:
                lines.append(
                    f"— {task.title}: тесты {task.reference_passed}/{task.tests_total} "
                    f"на эталоне, ошибку ловят {task.broken_failed} из них"
                )
            else:
                lines.append(f"— {task.title}: без тестов, {_first(task.issues) or 'тесты не просили'}")
        return "\n".join(lines)


def _first(issues: list[CheckIssue]) -> str:
    return issues[0].message if issues else ""


@dataclass
class GenerationResult:
    template: DraftTemplate
    report: GenerationReport
