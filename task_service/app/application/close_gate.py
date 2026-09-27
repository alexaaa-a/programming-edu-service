from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


PASS_SCORE = 8
MAX_ROUNDS = 2


@dataclass(frozen=True, slots=True)
class ReviewSnapshot:
    status: str
    score: float | None = None
    created_at: datetime | str | None = None
    reviewed_at: datetime | str | None = None
    failed_criteria: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CloseDecision:
    allowed: bool
    quality: str | None
    code: str
    reason: str


def normalize_score(raw: int | float) -> float:
    value = float(raw)
    if value > 10:
        value = value / 10.0
    return max(0.0, min(10.0, value))


def counts_toward_rounds(item: ReviewSnapshot) -> bool:
    status = (item.status or "").strip().lower()
    if status == "pending":
        return False
    if item.score is not None:
        return True
    if status == "failed" and item.reviewed_at is not None:
        return True
    return False


def evaluate_close(
        snapshots: Sequence[ReviewSnapshot] | None,
        pass_score: int = PASS_SCORE,
        max_rounds: int = MAX_ROUNDS,
) -> CloseDecision:
    items = _sorted(snapshots or [])
    if any((item.status or "").strip().lower() == "pending" for item in items):
        return CloseDecision(
            allowed=False,
            quality=None,
            code="pending",
            reason="Предыдущая сдача ещё на проверке — дождись отчёта.",
        )

    reviewed = [item for item in items if item.score is not None]
    spent_items = [item for item in items if counts_toward_rounds(item)]
    spent = len(spent_items)
    agent_failed = [
        item
        for item in spent_items
        if item.score is None and (item.status or "").strip().lower() == "failed"
    ]
    infra_failed = [
        item
        for item in items
        if (item.status or "").strip().lower() == "failed"
        and item.score is None
        and item.reviewed_at is None
    ]

    if not reviewed:
        if spent >= max_rounds:
            return CloseDecision(
                allowed=True,
                quality="weak",
                code="weak",
                reason="Лимит попыток исчерпан (в т.ч. сбои проверки). Можно закрыть задачу как слабую.",
            )
        if agent_failed or infra_failed:
            return CloseDecision(
                allowed=False,
                quality=None,
                code="revise",
                reason="Проверка не удалась. Отправь решение ещё раз — закрыть задачу пока нельзя.",
            )
        return CloseDecision(
            allowed=False,
            quality=None,
            code="need_review",
            reason="Сначала отправь решение на ревью команды.",
        )

    score = int(round(normalize_score(reviewed[-1].score or 0)))
    if score >= pass_score:
        return CloseDecision(
            allowed=True,
            quality="ok",
            code="ok",
            reason="Команда довольна. Можно закрыть задачу.",
        )
    if spent < max_rounds:
        return CloseDecision(
            allowed=False,
            quality=None,
            code="revise",
            reason="Балл ниже 8. Исправь замечания и сдайте снова — закрыть задачу пока нельзя.",
        )
    return CloseDecision(
        allowed=True,
        quality="weak",
        code="weak",
        reason="Лимит попыток исчерпан. Можно закрыть задачу как слабую.",
    )


def _sorted(items: Sequence[ReviewSnapshot]) -> list[ReviewSnapshot]:
    def key(item: ReviewSnapshot) -> str:
        stamp = item.created_at
        if stamp is None:
            return ""
        if isinstance(stamp, datetime):
            return stamp.isoformat()
        return str(stamp)

    return sorted(items, key=key)
