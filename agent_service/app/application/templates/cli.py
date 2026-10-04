import argparse
import asyncio
import json
import sys
from typing import Any

from agent_service.app.application.templates.checks import check_task, check_template
from agent_service.app.application.templates.models import (
    CheckIssue,
    DraftSprint,
    DraftTask,
    DraftTemplate,
)
from agent_service.app.application.tools.hidden_tests import run_hidden_tests


EMPTY_SOLUTION = "# пустое решение: тесты обязаны его завалить\n"


def load(path: str) -> DraftTemplate:
    with open(path, encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    sprints = []
    for index, raw in enumerate(data.get("sprints") or [], start=1):
        tasks = [
            DraftTask(
                title=str(task.get("title") or ""),
                description=str(task.get("description") or ""),
                tests=str(task.get("tests") or task.get("hidden_tests") or ""),
            )
            for task in (raw.get("tasks") or [])
        ]
        sprints.append(
            DraftSprint(order=int(raw.get("order") or index), title=str(raw.get("title") or ""), tasks=tasks)
        )
    return DraftTemplate(
        title=str(data.get("title") or ""),
        description=str(data.get("description") or ""),
        direction=str(data.get("direction") or ""),
        level=str(data.get("level") or ""),
        sprints=sprints,
    )


async def run_on_empty(draft: DraftTemplate) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    for task in draft.all_tasks():
        if not task.tests.strip():
            continue
        run = await run_hidden_tests(EMPTY_SOLUTION, task.tests)
        if run.status == "passed":
            issues.append(
                CheckIssue("tests_blind", "Тесты проходят на пустом решении", task.title)
            )
        elif run.status in {"timeout", "unavailable"}:
            issues.append(
                CheckIssue("run_failed", f"Прогон не состоялся: {run.detail or run.status}", task.title)
            )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка шаблона проекта")
    parser.add_argument("path", help="JSON шаблона")
    parser.add_argument("--run", action="store_true", help="прогнать тесты на пустом решении")
    args = parser.parse_args(argv)

    draft = load(args.path)
    issues = list(check_template(draft))
    for task in draft.all_tasks():
        issues.extend(
            check_task(task, with_tests=bool(task.tests.strip()), with_reference=False)
        )
    if args.run:
        issues.extend(asyncio.run(run_on_empty(draft)))

    tasks = draft.all_tasks()
    with_tests = sum(1 for task in tasks if task.tests.strip())
    print(f"{draft.title}: спринтов {len(draft.sprints)}, задач {len(tasks)}, с тестами {with_tests}")
    for issue in issues:
        where = f" [{issue.task}]" if issue.task else ""
        print(f"  {issue.code}{where}: {issue.message}")
    print("нарушений нет" if not issues else f"нарушений: {len(issues)}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
