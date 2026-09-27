from dataclasses import dataclass, field
from typing import Sequence

from agent_service.app.application.review.acceptance import CriterionCheck
from agent_service.app.application.review.adversarial import ChallengeVerdict
from agent_service.app.application.review.agent_path import mentor_leaked_solution
from agent_service.app.application.tools.models import ToolReport


DRAFT_HINTS = (
    "Вариант A: сделай акцент на открытых критериях приёмки и конкретных правках.",
    "Вариант B: сделай акцент на рисках/багах и как проверить исправление.",
    "Вариант C: короткий mentorship-тон, баланс критериев и практики без воды.",
)


@dataclass(frozen=True, slots=True)
class DraftScore:
    total: int
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SelectedDraft:
    text: str
    index: int
    score: int
    candidates: int
    reasons: list[str] = field(default_factory=list)


def needs_multi_draft(
        draft_final: int,
        checks: Sequence[CriterionCheck],
        challenge: ChallengeVerdict | None,
        report: ToolReport | None = None,
) -> bool:
    failed = sum(1 for item in checks if not item.passed)
    if failed >= 1:
        return True
    if draft_final <= 7:
        return True
    if challenge is not None and challenge.has_objections:
        return True
    if report is not None and (not report.syntax_ok or not report.compile_ok):
        return True
    if report is not None and report.tests_run and report.tests_passed is False:
        return True
    return False


def draft_count_for_case(
        draft_final: int,
        checks: Sequence[CriterionCheck],
        challenge: ChallengeVerdict | None,
        report: ToolReport | None = None,
        max_drafts: int = 3,
) -> int:
    if not needs_multi_draft(
        draft_final=draft_final,
        checks=checks,
        challenge=challenge,
        report=report,
    ):
        return 1
    return max(2, min(max_drafts, len(DRAFT_HINTS)))


def variant_hints(count: int) -> list[str]:
    n = max(1, min(count, len(DRAFT_HINTS)))
    return list(DRAFT_HINTS[:n])


def score_draft(
        text: str,
        checks: Sequence[CriterionCheck],
        challenge: ChallengeVerdict | None = None,
        report: ToolReport | None = None,
        final_score: int | None = None,
) -> DraftScore:
    body = (text or "").strip()
    reasons: list[str] = []
    total = 0
    if not body:
        return DraftScore(total=0, reasons=["пустой черновик"])

    length = len(body)
    if 180 <= length <= 650:
        total += 3
        reasons.append("длина в целевом диапазоне")
    elif 120 <= length < 180 or 650 < length <= 900:
        total += 1
        reasons.append("длина терпимая")
    else:
        reasons.append("длина вне удобного диапазона")

    lower = body.lower()
    failed = [item for item in checks if not item.passed]
    if failed:
        hits = 0
        for item in failed[:4]:
            tokens = _keywords(item.text)
            if tokens and any(token in lower for token in tokens[:3]):
                hits += 1
            elif item.note and any(tok in lower for tok in _keywords(item.note)[:2]):
                hits += 1
        total += min(4, hits * 2)
        if hits:
            reasons.append(f"закрывает открытые критерии ({hits})")
        else:
            reasons.append("не опирается на открытые критерии")
    else:
        total += 2
        reasons.append("критерии закрыты — общий разбор")

    actionable = ("добав", "замен", "проверь", "исправ", "убери", "напиши", "обработ")
    if any(marker in lower for marker in actionable):
        total += 2
        reasons.append("есть actionable правки")

    if mentor_leaked_solution(body):
        total -= 6
        reasons.append("слишком похоже на готовое решение")

    if report is not None:
        if (not report.syntax_ok or not report.compile_ok) and any(
            w in lower for w in ("синтакс", "компил", "не запуска")
        ):
            total += 2
            reasons.append("учёл поломку синтаксиса/компиляции")
        if report.tests_run and report.tests_passed is False and "тест" in lower:
            total += 1
            reasons.append("упомянул тесты")

    if challenge is not None and challenge.has_objections:
        tokens = []
        for item in challenge.challenges[:2] + challenge.missed[:2]:
            tokens.extend(_keywords(item)[:2])
        if tokens and any(token in lower for token in tokens):
            total += 2
            reasons.append("учёл возражения независимой проверки")

    if final_score is not None and str(final_score) in body:
        total += 1
        reasons.append("согласован с итоговым баллом")

    # Prefer Russian mentoring signals.
    if any(ch.isalpha() and "а" <= ch.lower() <= "я" for ch in body[:80]):
        total += 1

    return DraftScore(total=total, reasons=reasons)


def select_best_draft(
        drafts: Sequence[str],
        checks: Sequence[CriterionCheck],
        challenge: ChallengeVerdict | None = None,
        report: ToolReport | None = None,
        final_score: int | None = None,
) -> SelectedDraft:
    cleaned = [str(item or "").strip() for item in drafts if str(item or "").strip()]
    if not cleaned:
        return SelectedDraft(text="", index=0, score=0, candidates=0, reasons=["нет черновиков"])

    scored: list[tuple[int, int, DraftScore, str]] = []
    for index, text in enumerate(cleaned):
        verdict = score_draft(
            text,
            checks=checks,
            challenge=challenge,
            report=report,
            final_score=final_score,
        )
        scored.append((verdict.total, -index, verdict, text))
    scored.sort(reverse=True)
    best_total, _, best_verdict, best_text = scored[0]
    index = cleaned.index(best_text)
    return SelectedDraft(
        text=best_text,
        index=index,
        score=best_total,
        candidates=len(cleaned),
        reasons=best_verdict.reasons[:6],
    )


def _keywords(text: str) -> list[str]:
    stop = {
        "и",
        "или",
        "для",
        "при",
        "что",
        "это",
        "как",
        "если",
        "то",
        "на",
        "по",
        "из",
        "в",
        "с",
        "без",
        "не",
    }
    tokens = re_findall_words(text.lower())
    return [token for token in tokens if token not in stop and len(token) >= 4][:6]


def re_findall_words(text: str) -> list[str]:
    import re

    return re.findall(r"[a-zA-Zа-яА-Я_]{3,}", text)
