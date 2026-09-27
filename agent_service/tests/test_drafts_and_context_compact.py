from agent_service.app.application.review.acceptance import CriterionCheck
from agent_service.app.application.review.context_compact import (
    compact_agent_results,
    compact_huddle_briefing,
    compact_team_summary,
    compact_tool_facts,
)
from agent_service.app.application.review.draft_select import (
    draft_count_for_case,
    needs_multi_draft,
    score_draft,
    select_best_draft,
)
from agent_service.app.application.tools.models import ToolReport


def test_compact_tool_facts_keeps_priority_and_shrinks():
    bloated = "\n".join(
        [
            "Критерии приёмки по этой задаче:",
            "- [c1] вернуть сумму",
            "Язык: python",
            "Синтаксис: ok",
            "Компиляция: ok",
            "Находки:",
            "- [static/error] плохо",
        ]
        + [f"шумная строка {i} " + ("x" * 80) for i in range(40)]
    )
    compact = compact_tool_facts(bloated, max_chars=500)
    assert len(compact) < len(bloated)
    assert "Критерии приёмки" in compact or "Синтаксис" in compact
    assert "контекст сжат" in compact


def test_compact_agent_results_drops_verbose_fields():
    payload = {
        "reviewer_review": {"score": 8, "feedback": "ok " * 80, "suggestions": ["a", "b", "c", "d"]},
        "bug_review": {"score": 6, "feedback": "bug", "suggestions": []},
        "scorecard": {"final": 6},
        "acceptance_criteria": [
            {"id": "c1", "text": "вернуть сумму", "passed": False, "note": "нет"},
            {"id": "c2", "text": "тесты", "passed": True, "note": ""},
        ],
        "agent_path": {"steps": [{"name": "tools", "status": "ok", "detail": "long"}]},
        "tool_report": {
            "language": "python",
            "syntax_ok": True,
            "compile_ok": True,
            "findings": [{"tool": "static", "severity": "warning", "message": "warn"}],
        },
    }
    compact = compact_agent_results(payload)
    assert isinstance(compact, dict)
    assert compact["reviewer_review"]["score"] == 8
    assert len(compact["reviewer_review"]["suggestions"]) <= 3
    assert "acceptance_summary" in compact
    assert compact["acceptance_summary"]["failed"] == 1


def test_compact_team_summary_is_short_json():
    text = compact_team_summary(
        reviewer_score=8,
        reviewer_feedback="длинный " * 40,
        bug_score=5,
        bug_feedback="баг",
        checks=[{"id": "c1", "text": "валидация входа", "passed": False}],
    )
    assert "reviewer" in text
    assert len(text) < 800


def test_compact_huddle_briefing():
    briefing = "\n\n".join(
        f"Сара (аналитик):\n{'детали ' * 40}\nещё строка"
        for _ in range(4)
    )
    out = compact_huddle_briefing(briefing, max_chars=400)
    assert len(out) <= 450
    assert "Сара" in out


def test_needs_multi_draft_on_failed_criteria():
    checks = [CriterionCheck(id="c1", text="вернуть JSON", passed=False, required=True)]
    assert needs_multi_draft(draft_final=9, checks=checks, challenge=None) is True
    assert draft_count_for_case(draft_final=9, checks=checks, challenge=None) >= 2


def test_needs_single_draft_when_clean():
    checks = [CriterionCheck(id="c1", text="вернуть JSON", passed=True, required=True)]
    assert needs_multi_draft(draft_final=9, checks=checks, challenge=None) is False
    assert draft_count_for_case(draft_final=9, checks=checks, challenge=None) == 1


def test_select_best_draft_prefers_actionable_criteria_aligned():
    checks = [
        CriterionCheck(id="c1", text="обработка ValueError", passed=False, note="голый except"),
    ]
    weak = "В целом неплохо, подумайте ещё."
    strong = (
        "Итог 5/10. Не закрыта обработка ValueError: замени голый except на конкретный тип "
        "и проверь пустой ввод. Добавь тест на ошибку."
    )
    dump = (
        "Вот полное решение:\n```python\n"
        "def parse(v):\n"
        "    return int(v)\n"
        "def main():\n"
        "    print(parse(input()))\n"
        "def test_parse():\n"
        "    assert parse('1')==1\n"
        "```\n"
    )
    selected = select_best_draft(
        [weak, strong, dump],
        checks=checks,
        final_score=5,
    )
    assert selected.text == strong
    assert selected.candidates == 3
    assert selected.score >= score_draft(weak, checks=checks, final_score=5).total


def test_select_best_draft_accounts_for_tool_breakage():
    report = ToolReport(language="python", syntax_ok=False, compile_ok=False)
    good = "Код не компилируется из-за синтаксиса. Исправь скобки и проверь снова."
    bad = "Логика в целом понятна, можно чуть причесать имена."
    selected = select_best_draft([bad, good], checks=[], report=report)
    assert selected.text == good
