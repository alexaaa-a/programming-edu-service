import asyncio
import json
import logging

import pytest

from agent_service.app.application.templates.checks import (
    check_task,
    check_template,
    parse_criteria,
)
from agent_service.app.application.templates.models import (
    DraftSprint,
    DraftTask,
    DraftTemplate,
    TemplateSpec,
)
from agent_service.app.application.templates.parsing import (
    ParseError,
    compose_description,
    extract_json,
    sprint_from_payload,
    task_from_payload,
)
from agent_service.app.application.tools.hidden_tests import HiddenTestCase, HiddenTestRun
from agent_service.app.application.use_cases.generate_project_template import (
    GenerateProjectTemplateUseCase,
)


BRIEF = """Корзина считает итог заказа. Деньги хранятся в копейках, целыми числами.

```python
def order_total(items: list[dict], promo_percent: int = 0) -> int:
    ...
```

Каждая позиция: {"price": int, "qty": int}. Итог — сумма price * qty минус скидка
promo_percent процентов от всей суммы, округление вниз до копейки. Пустая корзина
стоит 0. promo_percent вне 0..100 — ValueError.

Критерии приёмки:
- Сумма считается как price * qty по всем позициям
- Скидка округляется вниз до копейки
- Пустая корзина возвращает 0 без ошибки
- promo_percent вне диапазона вызывает ValueError
"""

TESTS = """
import pytest
from solution import order_total


def test_sum():
    assert order_total([{"price": 100, "qty": 2}]) == 200


def test_discount_rounds_down():
    assert order_total([{"price": 1999, "qty": 3}], 15) == 5098


def test_empty_cart():
    assert order_total([]) == 0


def test_bad_promo():
    with pytest.raises(ValueError):
        order_total([], 101)
"""

REFERENCE = """
def order_total(items, promo_percent=0):
    if not 0 <= promo_percent <= 100:
        raise ValueError("promo_percent")
    total = sum(item["price"] * item["qty"] for item in items)
    return total - total * promo_percent // 100
"""

BROKEN = """
def order_total(items, promo_percent=0):
    if not 0 <= promo_percent <= 100:
        raise ValueError("promo_percent")
    total = sum(item["price"] * item["qty"] for item in items)
    return int(total * (1 - promo_percent / 100))
"""


def good_task(**over) -> DraftTask:
    task = DraftTask(
        title="Сумма заказа со скидкой",
        description=BRIEF,
        tests=TESTS,
        reference=REFERENCE,
        broken=BROKEN,
    )
    for key, value in over.items():
        setattr(task, key, value)
    return task


def test_a_good_task_passes_every_structural_check():
    assert check_task(good_task()) == []


def test_criteria_are_counted():
    few = BRIEF.replace("- Пустая корзина возвращает 0 без ошибки\n", "").replace(
        "- promo_percent вне диапазона вызывает ValueError\n", ""
    )
    codes = [issue.code for issue in check_task(good_task(description=few))]
    assert "criteria_count" in codes


def test_a_brief_without_the_criteria_block_is_rejected():
    without = BRIEF.replace("Критерии приёмки:", "Что проверяем:")
    codes = [issue.code for issue in check_task(good_task(description=without))]
    assert "criteria_missing" in codes


def test_the_brief_may_not_talk_about_the_board():
    text = BRIEF + "\nСпринт можно закрыть, когда задача принята.\n"
    issues = check_task(good_task(description=text))
    assert [issue.code for issue in issues] == ["board_words"]


def test_code_in_the_brief_must_parse():
    text = BRIEF.replace("def order_total(items: list[dict], promo_percent: int = 0) -> int:",
                         "def order_total(items: list[dict] promo_percent) ->:")
    codes = [issue.code for issue in check_task(good_task(description=text))]
    assert "brief_code" in codes


def test_reserved_and_malformed_titles_are_caught():
    assert "title_reserved" in [i.code for i in check_task(good_task(title="Ночной инцидент"))]
    assert "title_dash" in [i.code for i in check_task(good_task(title="Заказы — срезы"))]


def test_tests_must_import_the_solution_module():
    tests = TESTS.replace("from solution import order_total", "from app.cart import order_total")
    codes = [issue.code for issue in check_task(good_task(tests=tests))]
    assert "tests_import" in codes


def test_tests_may_not_reach_for_the_network_or_input():
    tests = TESTS + "\n\ndef test_live():\n    import requests\n    assert requests\n"
    codes = [issue.code for issue in check_task(good_task(tests=tests))]
    assert "tests_forbidden" in codes


def test_broken_test_file_is_reported_once_and_not_as_a_missing_assert():
    codes = [issue.code for issue in check_task(good_task(tests="def test_x(:\n    pass"))]
    assert codes == ["tests_syntax"]


def test_a_task_without_tests_still_passes_when_tests_were_not_asked_for():
    task = good_task(tests="", reference="", broken="")
    assert check_task(task, with_tests=False) == []
    assert [i.code for i in check_task(task, with_tests=True)] == ["tests_missing"]


def test_criteria_are_read_from_dashes_and_from_numbers():
    numbered = "Текст\n\nКритерии приёмки:\n1. Первый критерий тут\n2. Второй критерий тут\n"
    assert parse_criteria(numbered) == ["Первый критерий тут", "Второй критерий тут"]
    assert len(parse_criteria(BRIEF)) == 4
    assert parse_criteria("Без блока критериев") == []


def test_duplicate_task_titles_are_caught_across_sprints():
    draft = DraftTemplate(
        title="Проект",
        description="Мини-бэкенд магазина: заказы, деньги, ошибки и права.",
        direction="backend",
        level="junior",
        sprints=[
            DraftSprint(order=1, title="Первый", tasks=[good_task()]),
            DraftSprint(order=2, title="Второй", tasks=[good_task()]),
        ],
    )
    assert [issue.code for issue in check_template(draft)] == ["duplicate_title"]


def test_json_survives_fences_and_chatter():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Вот ответ: {"a": {"b": 2}} — готово') == {"a": {"b": 2}}
    with pytest.raises(ParseError):
        extract_json("никакого json")


def test_the_brief_is_assembled_in_a_fixed_order():
    text = compose_description(
        {
            "brief": "Условие",
            "signature": "def f():\n    ...",
            "rules": "Правила",
            "example": "2 + 2 = 4",
            "plan": ["Шаг"],
            "criteria": ["Первый критерий", "Второй критерий"],
        }
    )
    assert text.index("Условие") < text.index("```python") < text.index("Правила")
    assert "Пример: 2 + 2 = 4" in text
    assert text.strip().endswith("- Второй критерий")
    assert parse_criteria(text) == ["Первый критерий", "Второй критерий"]


def test_a_task_with_a_ready_description_is_taken_as_is():
    task = task_from_payload({"title": "Задача", "description": BRIEF, "tests": "```python\nx = 1\n```"})
    assert task.description == BRIEF.strip()
    assert task.tests.strip() == "x = 1"


def test_a_sprint_without_tasks_does_not_parse():
    with pytest.raises(ParseError):
        sprint_from_payload({"sprint": {"title": "Спринт", "tasks": []}}, 1)


class FakeLLM:
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        if not self.answers:
            raise AssertionError("лишний запрос к модели")
        return self.answers.pop(0)


def sprint_answer(tasks: list[dict], title: str = "Спринт про заказы") -> str:
    return json.dumps(
        {
            "title": "Сервис заказов",
            "description": "Мини-бэкенд магазина: заказы, деньги, ошибки.",
            "sprint": {"title": title, "tasks": tasks},
        },
        ensure_ascii=False,
    )


def task_payload(**over) -> dict:
    payload = {
        "title": "Сумма заказа со скидкой",
        "description": BRIEF,
        "tests": TESTS,
        "reference": REFERENCE,
        "broken": BROKEN,
    }
    payload.update(over)
    return payload


def runner_for(results: dict[str, HiddenTestRun], default: HiddenTestRun | None = None):
    async def run(code: str, tests: str) -> HiddenTestRun:
        for marker, result in results.items():
            if marker in code:
                return result
        if default is not None:
            return default
        raise AssertionError(f"нет заготовки для кода: {code[:40]}")

    return run


GREEN = HiddenTestRun(
    status="passed",
    total=4,
    passed=4,
    cases=[HiddenTestCase(name=f"test_{i}", passed=True) for i in range(4)],
)
RED = HiddenTestRun(
    status="failed",
    total=4,
    passed=3,
    failed=1,
    cases=[HiddenTestCase(name="test_discount_rounds_down", passed=False, message="assert 5097 == 5098")],
)


def use_case(llm: FakeLLM, runner, rounds: int = 1) -> GenerateProjectTemplateUseCase:
    return GenerateProjectTemplateUseCase(
        llm=llm,
        logger=logging.getLogger("test"),
        runner=runner,
        max_rounds=rounds,
    )


def test_a_checked_sprint_comes_back_with_its_numbers():
    llm = FakeLLM([sprint_answer([task_payload()])])
    runner = runner_for({"// 100": GREEN, "1 - promo_percent / 100": RED})
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, runner).generate_sprint(spec, 1, []))

    assert result.report.ok is True
    assert result.project_title == "Сервис заказов"
    assert result.sprint is not None and len(result.sprint.tasks) == 1
    report = result.report.tasks[0]
    assert (report.tests_total, report.reference_passed, report.broken_failed) == (4, 4, 1)
    assert report.tests_kept is True and report.attempts == 1


def test_tests_that_pass_on_the_broken_solution_are_not_published():
    llm = FakeLLM([sprint_answer([task_payload()]), sprint_answer([task_payload()])])
    runner = runner_for({}, default=GREEN)
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, runner, rounds=0).generate_sprint(spec, 1, []))

    report = result.report.tasks[0]
    assert report.ok is False and report.dropped is False
    assert report.tests_kept is False
    assert [issue.code for issue in report.issues] == ["tests_blind"]
    assert result.sprint is not None
    assert result.sprint.tasks[0].tests == ""
    assert result.report.ok is False


def test_a_failing_reference_is_sent_back_for_a_fix():
    fixed = dict(task_payload(), reference=REFERENCE.replace("// 100", "// 100  # fixed"))
    llm = FakeLLM([sprint_answer([task_payload(reference=BROKEN)]), json.dumps(fixed, ensure_ascii=False)])
    runner = runner_for({"# fixed": GREEN, "1 - promo_percent / 100": RED})
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, runner).generate_sprint(spec, 1, []))

    assert result.report.ok is True
    assert result.report.tasks[0].attempts == 2
    assert "Эталонное решение не проходит свои тесты" in llm.prompts[1]


def test_a_task_that_stays_broken_is_dropped_not_published():
    bad = task_payload(description="Коротко", title="Задача")
    llm = FakeLLM([sprint_answer([bad, task_payload()]), json.dumps(bad, ensure_ascii=False)])
    runner = runner_for({"// 100": GREEN, "1 - promo_percent / 100": RED})
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=2)

    result = asyncio.run(use_case(llm, runner).generate_sprint(spec, 1, []))

    dropped = result.report.tasks[0]
    assert dropped.dropped is True and dropped.ok is False
    assert result.sprint is not None and len(result.sprint.tasks) == 1
    assert result.report.ok is False
    assert "снята" in result.report.as_text()


def test_a_sprint_the_model_mangled_is_reported_not_raised():
    llm = FakeLLM(["не могу"])
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, runner_for({}, default=GREEN)).generate_sprint(spec, 1, []))

    assert result.sprint is None
    assert result.report.ok is False
    assert [issue.code for issue in result.report.issues] == ["sprint_failed"]


def test_the_whole_template_keeps_sprints_in_order_and_titles_apart():
    second = task_payload(title="Статусы заказа")
    llm = FakeLLM([sprint_answer([task_payload()]), sprint_answer([second], title="Спринт два")])
    runner = runner_for({"// 100": GREEN, "1 - promo_percent / 100": RED})
    spec = TemplateSpec(topic="Сервис заказов", sprints=2, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, runner)(spec))

    template = result.template.as_template()
    assert [sprint["order"] for sprint in template["sprints"]] == [1, 2]
    assert template["title"] == "Сервис заказов"
    assert template["sprints"][0]["tasks"][0]["tests"].strip().startswith("import pytest")
    assert "Сумма заказа со скидкой" in llm.prompts[1]
    assert result.report.ok is True
    assert result.report.with_tests == 2


def test_the_payload_never_carries_the_reference_solution():
    llm = FakeLLM([sprint_answer([task_payload()])])
    runner = runner_for({"// 100": GREEN, "1 - promo_percent / 100": RED})
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, runner)(spec))

    dumped = json.dumps(result.template.as_template(), ensure_ascii=False)
    assert "promo_percent / 100" not in dumped  # сломанное решение
    assert "total * promo_percent // 100" not in dumped  # эталон
    assert set(result.template.as_template()["sprints"][0]["tasks"][0]) == {
        "title",
        "description",
        "tests",
    }


def test_the_spec_is_clamped_to_something_sane():
    spec = TemplateSpec(topic=" " + "а" * 400, sprints=99, tasks_per_sprint=0).normalized()
    assert spec.sprints == 5 and spec.tasks_per_sprint == 2
    assert len(spec.topic) == 200


def test_the_self_check_really_runs_the_code():
    llm = FakeLLM([sprint_answer([task_payload()])])
    spec = TemplateSpec(topic="Сервис заказов", sprints=1, tasks_per_sprint=1)

    result = asyncio.run(use_case(llm, None)(spec))

    report = result.report.tasks[0]
    assert result.report.ok is True
    assert (report.tests_total, report.reference_passed) == (4, 4)
    assert report.broken_failed == 1


def write_template(tmp_path, tests: str) -> str:
    payload = {
        "project_template_id": 1,
        "title": "Сервис заказов",
        "description": "Мини-бэкенд магазина: заказы, деньги, ошибки.",
        "direction": "backend",
        "level": "junior",
        "sprints": [
            {
                "order": 1,
                "title": "Спринт 1",
                "tasks": [{"title": "Сумма заказа со скидкой", "description": BRIEF, "tests": tests}],
            }
        ],
    }
    path = tmp_path / "template.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_a_published_template_passes_without_a_reference_solution(tmp_path, capsys):
    from agent_service.app.application.templates.cli import main

    assert main([write_template(tmp_path, TESTS)]) == 0
    assert "нарушений нет" in capsys.readouterr().out


def test_tests_that_go_green_on_an_empty_solution_are_caught(tmp_path, capsys):
    from agent_service.app.application.templates.cli import main

    blind = (
        "import pytest\n"
        "import solution\n\n\n"
        "def test_module_exists():\n    assert solution is not None\n\n\n"
        "def test_true():\n    assert True\n\n\n"
        "def test_also_true():\n    assert 1 + 1 == 2\n"
    )
    assert main([write_template(tmp_path, blind), "--run"]) == 1
    assert "Тесты проходят на пустом решении" in capsys.readouterr().out
