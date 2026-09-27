from agent_service.app.application.review.acceptance import (
    AcceptanceCriterion,
    AcceptanceRubric,
    CriterionCheck,
    build_rubric_heuristic,
    format_checks_for_feedback,
    review_brief,
    rubric_score_and_cap,
)
from agent_service.app.application.review.scorecard import compose_score


def test_build_rubric_heuristic_from_task_bullets():
    rubric = build_rubric_heuristic(
        "Напиши функцию parse_int.\n"
        "Должна возвращать int.\n"
        "Нужно обрабатывать ValueError без голого except."
    )
    assert len(rubric.criteria) >= 2
    assert all(item.id.startswith("c") for item in rubric.criteria)
    assert all(item.required for item in rubric.criteria)


def test_rubric_score_caps_when_required_fail():
    checks = [
        CriterionCheck(id="c1", text="API endpoint", passed=True, required=True),
        CriterionCheck(id="c2", text="валидация", passed=False, required=True),
        CriterionCheck(id="c3", text="тесты", passed=False, required=True),
    ]
    score, cap, reasons = rubric_score_and_cap(checks)
    assert score == 4
    assert cap == 4
    assert any("потолок 5" in item for item in reasons)


def test_compose_score_respects_failed_required_criteria():
    checks = [
        CriterionCheck(id="c1", text="вернуть JSON", passed=False, required=True),
        CriterionCheck(id="c2", text="статус 200", passed=True, required=True),
        CriterionCheck(id="c3", text="логирование", passed=True, required=True),
    ]
    card = compose_score(task=9, reliability=9, checks=checks)
    assert card.rubric is not None
    assert card.final <= 7
    assert card.rubric_cap == 7


def test_format_checks_for_feedback_marks_pass_fail():
    text = format_checks_for_feedback(
        [
            CriterionCheck(id="c1", text="есть handler", passed=True, note="ok"),
            CriterionCheck(id="c2", text="есть тесты", passed=False, note="нет"),
        ]
    )
    assert "✓ есть handler" in text
    assert "✗ есть тесты" in text


def test_empty_rubric_does_not_cap_score():
    card = compose_score(task=8, reliability=8, checks=[])
    assert card.rubric is None
    assert card.final == 8


def test_night_incident_board_rules_are_not_code_criteria():
    old = (
        "Ночь. Эмма пишет: на проде 500.\n\n"
        "def discounted(price: int, percent: int) -> int:\n"
        "    return price // percent\n\n"
        "Почини падение. Пока задача в «к выполнению», спринт можно закрыть без неё. "
        "Если взял в работу — доведи до закрытия. "
        "Полный зачёт даёт в письме разовую премию 15000. "
        "Слабое закрытие и молчание премию не дают, оклад тот же."
    )
    brief = review_brief(old)
    assert "price // percent" in brief
    assert "спринт" not in brief.lower()
    assert "преми" not in brief.lower()
    assert "оклад" not in brief.lower()
    rubric = build_rubric_heuristic(old)
    joined = " ".join(item.text for item in rubric.criteria).lower()
    assert "преми" not in joined
    assert "спринт" not in joined
    assert "оклад" not in joined


def test_acceptance_rubric_prompt_block():
    block = AcceptanceRubric(
        criteria=[
            AcceptanceCriterion(id="c1", text="вернуть число", required=True),
        ]
    ).as_prompt_block()
    assert "Критерии приёмки" in block
    assert "[c1]" in block
    assert "вернуть число" in block
