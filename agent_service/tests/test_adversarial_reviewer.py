from agent_service.app.application.review.adversarial import (
    ChallengeVerdict,
    adversarial_cap_and_reasons,
    format_challenges_for_feedback,
    heuristic_challenge,
    parse_challenge_verdict,
)
from agent_service.app.application.review.scorecard import compose_score


def test_parse_challenge_verdict_disagrees_with_cap():
    verdict = parse_challenge_verdict(
        '{"agrees": false, "severity": "high", "score_cap": 4, '
        '"challenges": ["Нет обработки None"], "missed": ["пустой ввод"], '
        '"feedback": "Оценка завышена"}'
    )
    assert verdict.agrees is False
    assert verdict.severity == "high"
    assert verdict.score_cap == 4
    assert "None" in verdict.challenges[0]


def test_heuristic_challenges_inflated_score_on_broken_syntax():
    verdict = heuristic_challenge(
        team_task_score=8,
        team_reliability_score=7,
        syntax_ok=False,
        compile_ok=False,
    )
    assert verdict.has_objections
    assert verdict.severity == "high"
    assert verdict.score_cap == 2


def test_compose_score_applies_adversarial_cap():
    verdict = ChallengeVerdict(
        agrees=False,
        severity="high",
        score_cap=5,
        challenges=["Пропущен edge case"],
        missed=[],
        feedback="Не согласен",
    )
    card = compose_score(task=9, reliability=9, adversarial=verdict)
    assert card.adversarial_cap == 5
    assert card.final <= 5
    assert any("состязательн" in item for item in card.reasons)


def test_adversarial_medium_default_cap():
    verdict = ChallengeVerdict(
        agrees=False,
        severity="medium",
        score_cap=None,
        challenges=["Слабая валидация"],
    )
    cap, reasons = adversarial_cap_and_reasons(verdict)
    assert cap == 7
    assert any("потолок 7" in item for item in reasons)


def test_format_challenges_for_feedback():
    text = format_challenges_for_feedback(
        ChallengeVerdict(
            agrees=False,
            severity="medium",
            challenges=["Нет тестов"],
            missed=["логирование ошибок"],
            feedback="Есть возражения",
        )
    )
    assert "Независимая проверка" in text
    assert "Нет тестов" in text
    assert "логирование" in text


def test_agreeing_verdict_does_not_cap():
    card = compose_score(
        task=8,
        reliability=8,
        adversarial=ChallengeVerdict(agrees=True, severity="low"),
    )
    assert card.adversarial_cap is None
    assert card.final == 8
