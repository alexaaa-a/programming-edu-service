import ast
import re

from agent_service.app.application.templates.models import (
    RESERVED_TITLES,
    CheckIssue,
    DraftTask,
    DraftTemplate,
)


MIN_CRITERIA = 3
MAX_CRITERIA = 6
MIN_DESCRIPTION = 180
MAX_DESCRIPTION = 4000
MIN_TESTS = 3
MAX_TITLE = 70

CRITERIA_HEADER = "Критерии приёмки:"

BOARD_WORDS = re.compile(
    r"спринт можно закрыть|взял\w* в работу|довед\w* до закрытия|разов\w+ преми"
    r"|\bоклад\b|слабое закрытие|на доске|грейд\b",
    re.IGNORECASE,
)

FORBIDDEN_IN_TESTS = re.compile(
    r"\binput\s*\(|\bimport\s+(requests|socket|urllib|http\.client|subprocess)"
    r"|\bopen\s*\(\s*[\"']/(?!tmp)",
)

CODE_BLOCK = re.compile(r"```(?:python|py)?\n(.*?)```", re.DOTALL)


def check_template(draft: DraftTemplate, expected_tasks: int | None = None) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if not draft.title.strip():
        issues.append(CheckIssue("template_title", "У шаблона нет названия"))
    elif len(draft.title) > 90:
        issues.append(CheckIssue("template_title", "Название шаблона длиннее 90 символов"))
    if len(draft.description.strip()) < 40:
        issues.append(CheckIssue("template_description", "Описание шаблона короче 40 символов"))

    if not draft.sprints:
        issues.append(CheckIssue("no_sprints", "В шаблоне нет спринтов"))
    orders = [sprint.order for sprint in draft.sprints]
    if len(set(orders)) != len(orders):
        issues.append(CheckIssue("sprint_order", "Номера спринтов повторяются"))
    for sprint in draft.sprints:
        if not sprint.title.strip():
            issues.append(CheckIssue("sprint_title", f"Спринт {sprint.order} без названия"))
        if not sprint.tasks:
            issues.append(CheckIssue("empty_sprint", f"В спринте {sprint.order} нет задач"))

    seen: set[str] = set()
    for task in draft.all_tasks():
        key = task.title.strip().casefold()
        if key and key in seen:
            issues.append(
                CheckIssue("duplicate_title", f"Задача «{task.title}» встречается дважды", task.title)
            )
        seen.add(key)

    total = len(draft.all_tasks())
    if expected_tasks is not None and total < expected_tasks:
        issues.append(
            CheckIssue(
                "task_count",
                f"Задач {total}, просили {expected_tasks}",
            )
        )
    return issues


def check_task(
        task: DraftTask,
        with_tests: bool = True,
        with_reference: bool = True,
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    title = task.title.strip()
    name = title or "без названия"

    if not title:
        issues.append(CheckIssue("title_empty", "У задачи нет названия", name))
    if len(title) > MAX_TITLE:
        issues.append(CheckIssue("title_long", f"Название длиннее {MAX_TITLE} символов", name))
    if title in RESERVED_TITLES:
        issues.append(
            CheckIssue("title_reserved", f"Название «{title}» занято карьерным слоем", name)
        )
    if "—" in title or "–" in title:
        issues.append(CheckIssue("title_dash", "В названии тире, оно ломает вёрстку доски", name))

    description = task.description.strip()
    if len(description) < MIN_DESCRIPTION:
        issues.append(
            CheckIssue("brief_short", f"Бриф короче {MIN_DESCRIPTION} символов", name)
        )
    if len(description) > MAX_DESCRIPTION:
        issues.append(
            CheckIssue("brief_long", f"Бриф длиннее {MAX_DESCRIPTION} символов", name)
        )

    board = BOARD_WORDS.search(description)
    if board:
        issues.append(
            CheckIssue(
                "board_words",
                f"В брифе правила доски: «{board.group(0)}». Задача про код, а не про процесс",
                name,
            )
        )

    criteria = parse_criteria(description)
    if not criteria:
        issues.append(
            CheckIssue("criteria_missing", f"В брифе нет блока «{CRITERIA_HEADER}»", name)
        )
    elif not MIN_CRITERIA <= len(criteria) <= MAX_CRITERIA:
        issues.append(
            CheckIssue(
                "criteria_count",
                f"Критериев {len(criteria)}, нужно от {MIN_CRITERIA} до {MAX_CRITERIA}",
                name,
            )
        )
    for criterion in criteria:
        if len(criterion) < 12:
            issues.append(
                CheckIssue("criterion_short", f"Критерий «{criterion}» ничего не проверяет", name)
            )
            break

    for index, block in enumerate(CODE_BLOCK.findall(description), start=1):
        error = syntax_error(block)
        if error:
            issues.append(
                CheckIssue("brief_code", f"Код в брифе (блок {index}) не разбирается: {error}", name)
            )

    if with_tests:
        issues.extend(check_tests(task, with_reference=with_reference))
    return issues


def check_tests(task: DraftTask, with_reference: bool = True) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    name = task.title.strip() or "без названия"
    tests = task.tests.strip()
    reference = task.reference.strip()

    if not tests:
        issues.append(CheckIssue("tests_missing", "Нет тестов", name))
        return issues

    error = syntax_error(tests)
    if error:
        issues.append(CheckIssue("tests_syntax", f"Тесты не разбираются: {error}", name))
        return issues

    functions = test_functions(tests)
    if len(functions) < MIN_TESTS:
        issues.append(
            CheckIssue("tests_few", f"Тестов {len(functions)}, нужно хотя бы {MIN_TESTS}", name)
        )
    if not _has_assert(tests):
        issues.append(CheckIssue("tests_no_assert", "В тестах нет ни одной проверки", name))
    if "from solution import" not in tests and "import solution" not in tests:
        issues.append(
            CheckIssue("tests_import", "Тесты должны брать решение из модуля solution", name)
        )
    forbidden = FORBIDDEN_IN_TESTS.search(tests)
    if forbidden:
        issues.append(
            CheckIssue(
                "tests_forbidden",
                f"В тестах есть «{forbidden.group(0).strip()}»: в песочнице нет сети и ввода",
                name,
            )
        )

    if not with_reference:
        return issues
    if not reference:
        issues.append(CheckIssue("reference_missing", "Нет эталонного решения", name))
    else:
        error = syntax_error(reference)
        if error:
            issues.append(
                CheckIssue("reference_syntax", f"Эталонное решение не разбирается: {error}", name)
            )
    if task.broken.strip():
        error = syntax_error(task.broken)
        if error:
            issues.append(
                CheckIssue("broken_syntax", f"Сломанное решение не разбирается: {error}", name)
            )
    return issues


def parse_criteria(description: str) -> list[str]:
    lower = description.lower()
    marker = lower.find(CRITERIA_HEADER.lower())
    if marker < 0:
        return []
    tail = description[marker + len(CRITERIA_HEADER):]
    criteria: list[str] = []
    for raw in tail.splitlines():
        line = raw.strip()
        if not line:
            if criteria:
                break
            continue
        if line.startswith(("-", "*", "•")):
            criteria.append(line.lstrip("-*• ").strip())
            continue
        if re.match(r"^\d+[.)]\s+", line):
            criteria.append(re.sub(r"^\d+[.)]\s+", "", line).strip())
            continue
        break
    return [item for item in criteria if item]


def test_functions(tests: str) -> list[str]:
    try:
        tree = ast.parse(tests)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            names.append(node.name)
    return names


def syntax_error(code: str) -> str:
    text = (code or "").strip()
    if not text:
        return "пусто"
    try:
        ast.parse(text)
    except SyntaxError as e:
        line = e.lineno or 0
        return f"{e.msg} (строка {line})"
    return ""


def _has_assert(tests: str) -> bool:
    try:
        tree = ast.parse(tests)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Attribute) and node.attr in {"raises", "warns", "approx"}:
            return True
    return False
