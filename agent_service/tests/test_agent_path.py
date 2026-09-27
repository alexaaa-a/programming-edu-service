from agent_service.app.application.review.agent_path import (
    AgentPath,
    evaluate_chat_path,
    evaluate_review_path,
    mentor_leaked_solution,
)
from agent_service.app.application.review.scorecard import compose_score


def _healthy_review_path() -> AgentPath:
    path = AgentPath()
    for name in (
        "tools",
        "acceptance_rubric",
        "reviewer",
        "bug",
        "grade_rubric",
        "adversarial",
        "mentor",
    ):
        kind = "agent" if name in {"reviewer", "bug", "adversarial", "mentor"} else "step"
        if name == "tools":
            kind = "tool"
        path.record(name, kind=kind, status="ok")
    path.record("static", kind="tool", status="ok")
    path.record("sandbox", kind="tool", status="ok")
    return path


def test_healthy_review_path_scores_high():
    verdict = evaluate_review_path(
        _healthy_review_path(),
        language="python",
        tools_ran=True,
        syntax_checked=True,
        compile_checked=True,
        sandbox_eligible=True,
        mentor_feedback="Коротко: добавь проверку на пустой ввод.",
    )
    assert verdict.ok
    assert verdict.score >= 9
    assert verdict.cap is None


def test_missing_steps_and_skipped_tools_cap_score():
    path = AgentPath()
    path.record("reviewer", kind="agent", status="ok")
    verdict = evaluate_review_path(
        path,
        language="python",
        tools_ran=False,
        syntax_checked=False,
        compile_checked=False,
        sandbox_eligible=True,
        mentor_feedback="ok",
    )
    assert not verdict.ok
    assert verdict.score <= 6
    assert any("инструменты" in item for item in verdict.violations)


def test_mentor_solution_leak_detected():
    dump = """
Вот полное решение:

```python
def parse(value):
    if not value:
        raise ValueError('empty')
    return int(value)

def main():
    print(parse(input()))

def test_parse():
    assert parse('1') == 1
```
"""
    assert mentor_leaked_solution(dump)
    verdict = evaluate_review_path(
        _healthy_review_path(),
        language="python",
        tools_ran=True,
        syntax_checked=True,
        compile_checked=True,
        sandbox_eligible=True,
        mentor_feedback=dump,
    )
    assert any("готовое решение" in item or "полный код" in item for item in verdict.violations)
    assert verdict.cap is not None and verdict.cap <= 5


def test_compose_score_applies_process_cap():
    path = AgentPath()
    for name in ("tools", "acceptance_rubric", "reviewer", "bug", "grade_rubric", "adversarial", "mentor"):
        path.record(name, status="ok")
    verdict = evaluate_review_path(
        path,
        language="python",
        tools_ran=False,
        syntax_checked=False,
        compile_checked=False,
        sandbox_eligible=True,
        mentor_feedback="ok",
    )
    card = compose_score(task=9, reliability=9, path=verdict)
    assert card.process is not None
    assert card.final <= card.process
    if card.process_cap is not None:
        assert card.final <= card.process_cap


def test_chat_huddle_without_advisors_is_bad_path():
    verdict = evaluate_chat_path(mode="huddle", speaker_id="john", advisors=[], answer="Привет")
    assert not verdict.ok
    assert any("советник" in item for item in verdict.violations)


def test_chat_solo_path_ok():
    verdict = evaluate_chat_path(mode="solo", speaker_id="emma", advisors=[], answer="Проверь except")
    assert verdict.ok
    assert verdict.score >= 9
