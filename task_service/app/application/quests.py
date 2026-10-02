from dataclasses import dataclass, replace
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class CareerProgress:
    closes_ok: int = 0
    closes_weak: int = 0
    streak_ok: int = 0
    best_streak: int = 0
    first_try: int = 0
    nines: int = 0
    peer_found: int = 0
    incidents_done: int = 0
    demos_held: int = 0
    sprints: int = 0
    promotions: int = 0
    purchases: int = 0

    @property
    def closes(self) -> int:
        return self.closes_ok + self.closes_weak


@dataclass(frozen=True, slots=True)
class CareerBadge:
    id: str
    at: datetime


@dataclass(frozen=True, slots=True)
class BadgeDef:
    id: str
    title: str
    hint: str
    metric: str
    target: int


@dataclass(frozen=True, slots=True)
class Quest:
    id: str
    title: str
    hint: str
    current: int
    target: int

    @property
    def left(self) -> int:
        return max(self.target - self.current, 0)


BADGES: tuple[BadgeDef, ...] = (
    BadgeDef(
        id="first_close",
        title="Первый зачёт",
        hint="Закрой задачу с зачётом",
        metric="closes_ok",
        target=1,
    ),
    BadgeDef(
        id="first_try",
        title="С первой сдачи",
        hint="Закрой задачу, не отправляя её на второй круг",
        metric="first_try",
        target=1,
    ),
    BadgeDef(
        id="nine",
        title="Девятка",
        hint="Получи 9 или 10 за сдачу",
        metric="nines",
        target=1,
    ),
    BadgeDef(
        id="streak_three",
        title="Три подряд",
        hint="Три зачёта подряд, без слабых закрытий между ними",
        metric="best_streak",
        target=3,
    ),
    BadgeDef(
        id="bug_hunter",
        title="Чужой баг",
        hint="Найди настоящую дыру на ревью кода стажёра",
        metric="peer_found",
        target=1,
    ),
    BadgeDef(
        id="firefighter",
        title="Ночной дежурный",
        hint="Разберись с ночным инцидентом на проде",
        metric="incidents_done",
        target=1,
    ),
    BadgeDef(
        id="pitch",
        title="Питч держится",
        hint="Пройди пятничное демо так, чтобы питч засчитали",
        metric="demos_held",
        target=1,
    ),
    BadgeDef(
        id="promoted",
        title="Первое повышение",
        hint="Получи письмо с повышением грейда",
        metric="promotions",
        target=1,
    ),
    BadgeDef(
        id="investor",
        title="Вложился в себя",
        hint="Потрать премию на дополнительный круг, сессию с Эммой или критерии",
        metric="purchases",
        target=1,
    ),
    BadgeDef(
        id="streak_five",
        title="Серия из пяти",
        hint="Пять зачётов подряд",
        metric="best_streak",
        target=5,
    ),
    BadgeDef(
        id="veteran",
        title="Три спринта",
        hint="Закрой три спринта",
        metric="sprints",
        target=3,
    ),
)

BADGE_BY_ID: dict[str, BadgeDef] = {badge.id: badge for badge in BADGES}

MAX_ACTIVE_QUESTS = 3


def metric_value(progress: CareerProgress, metric: str) -> int:
    return int(getattr(progress, metric, 0) or 0)


def award(
        progress: CareerProgress,
        earned: tuple[CareerBadge, ...],
        now: datetime | None = None,
) -> tuple[tuple[CareerBadge, ...], tuple[str, ...]]:
    stamp = now or datetime.now(tz=timezone.utc)
    have = {badge.id for badge in earned}
    fresh: list[CareerBadge] = []
    for badge in BADGES:
        if badge.id in have:
            continue
        if metric_value(progress, badge.metric) >= badge.target:
            fresh.append(CareerBadge(id=badge.id, at=stamp))
    if not fresh:
        return earned, ()
    return earned + tuple(fresh), tuple(badge.id for badge in fresh)


def quests(
        progress: CareerProgress,
        earned: tuple[CareerBadge, ...],
        limit: int = MAX_ACTIVE_QUESTS,
) -> tuple[Quest, ...]:
    have = {badge.id for badge in earned}
    open_quests: list[Quest] = []
    for badge in BADGES:
        if badge.id in have:
            continue
        current = min(metric_value(progress, badge.metric), badge.target)
        open_quests.append(
            Quest(
                id=badge.id,
                title=badge.title,
                hint=badge.hint,
                current=current,
                target=badge.target,
            )
        )
    open_quests.sort(key=lambda item: (item.left, -item.current / item.target))
    return tuple(open_quests[:limit])


def apply_close(
        progress: CareerProgress,
        quality: str | None,
        score: float | None = None,
        attempts: int = 0,
) -> CareerProgress:
    if (quality or "").strip().lower() == "ok":
        streak = progress.streak_ok + 1
        updated = replace(
            progress,
            closes_ok=progress.closes_ok + 1,
            streak_ok=streak,
            best_streak=max(progress.best_streak, streak),
        )
        if attempts == 1:
            updated = replace(updated, first_try=updated.first_try + 1)
        if score is not None and score >= 9.0:
            updated = replace(updated, nines=updated.nines + 1)
        return updated
    return replace(
        progress,
        closes_weak=progress.closes_weak + 1,
        streak_ok=0,
    )


def apply_peer_review(progress: CareerProgress, found: bool) -> CareerProgress:
    if not found:
        return progress
    return replace(progress, peer_found=progress.peer_found + 1)


def apply_demo(
        progress: CareerProgress,
        held: bool,
        incident: str | None = None,
) -> CareerProgress:
    updated = progress
    if held:
        updated = replace(updated, demos_held=updated.demos_held + 1)
    if (incident or "").strip().lower() == "done":
        updated = replace(updated, incidents_done=updated.incidents_done + 1)
    return updated


def apply_sprint(progress: CareerProgress, promoted: bool) -> CareerProgress:
    updated = replace(progress, sprints=progress.sprints + 1)
    if promoted:
        updated = replace(updated, promotions=updated.promotions + 1)
    return updated


def apply_purchase(progress: CareerProgress) -> CareerProgress:
    return replace(progress, purchases=progress.purchases + 1)


def badge_payload(ids: tuple[str, ...] | list[str]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for badge_id in ids:
        badge = BADGE_BY_ID.get(str(badge_id))
        if badge is not None:
            payload.append({"id": badge.id, "title": badge.title, "hint": badge.hint})
    return payload
