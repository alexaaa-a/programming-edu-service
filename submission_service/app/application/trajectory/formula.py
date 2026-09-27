from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Sequence

from submission_service.app.application.dto.submission import SubmissionDTO


Action = Literal[
    "start",
    "wait_review",
    "revise",
    "chat",
    "close_ok",
    "close_weak",
    "next_task",
    "hold_sprint",
    "next_sprint",
]


@dataclass(frozen=True, slots=True)
class TrajectoryConfig:
    window: int = 8
    decay: float = 0.7
    pass_score: int = 8
    low_score: int = 5
    r_next: float = 0.7
    r_sprint: float = 0.75
    d_hard: float = 0.5
    activity_days: int = 2
    weight_m: float = 0.5
    weight_d: float = 0.3
    weight_p: float = 0.2
    max_rounds: int = 2
    criteria_blend: float = 0.3


@dataclass(frozen=True, slots=True)
class TrajectoryResult:
    mastery: float
    difficulty: float
    pace: float
    readiness: float
    action: Action
    reason: str
    block_close: bool
    block_next_sprint: bool
    window_tasks: int = 0
    reviewed_in_window: int = 0
    current_task_id: int | None = None
    current_attempts: int = 0
    current_score: int | None = None
    failed_criteria: list[str] = field(default_factory=list)


def normalize_score(raw: int | float) -> float:
    value = float(raw)
    if value > 10:
        value = value / 10.0
    return max(0.0, min(10.0, value))


def compute_trajectory(
        submissions: Sequence[SubmissionDTO] | None,
        task_id: int | None = None,
        now: datetime | None = None,
        config: TrajectoryConfig | None = None,
        current_task_status: str | None = None,
) -> TrajectoryResult:
    cfg = config or TrajectoryConfig()
    stamp = now or datetime.now(tz=timezone.utc)
    items = list(submissions or [])
    if not items:
        return TrajectoryResult(
            mastery=0.0,
            difficulty=0.0,
            pace=0.0,
            readiness=0.0,
            action="start",
            reason="Ещё нет сдач — возьми первую задачу пути.",
            block_close=True,
            block_next_sprint=True,
        )

    ordered = sorted(items, key=_created_at)
    reviewed = [item for item in ordered if item.review is not None]
    window = reviewed[-cfg.window :] if reviewed else []
    window_task_ids = list(dict.fromkeys(item.task_id for item in window))
    latest_by_task = _latest_reviewed_by_task(reviewed)

    mastery = _mastery(window, cfg)
    difficulty = _difficulty(ordered, window_task_ids, latest_by_task, cfg)
    pace = _pace(latest_by_task, window_task_ids, ordered, stamp, cfg)
    readiness = _clamp(
        cfg.weight_m * mastery
        + cfg.weight_d * (1.0 - difficulty)
        + cfg.weight_p * pace
    )

    current_id = task_id if task_id is not None else _latest_task_id(ordered)
    current_subs = [item for item in ordered if item.task_id == current_id] if current_id else []
    current_reviewed = [item for item in current_subs if item.review is not None]
    current_score = (
        int(round(normalize_score(current_reviewed[-1].review.score)))
        if current_reviewed and current_reviewed[-1].review is not None
        else None
    )
    current_attempts = sum(1 for item in current_subs if _counts_toward_rounds(item))
    pending = any(item.status == "pending" for item in current_subs)
    failed_criteria = _failed_criteria(current_reviewed[-1] if current_reviewed else None)
    criteria_rate = _criteria_rate(current_reviewed[-1] if current_reviewed else None)
    all_mastered = bool(window_task_ids) and all(
        _task_score(latest_by_task.get(tid)) >= cfg.pass_score for tid in window_task_ids
    )

    action, reason, block_close, block_next = _decide_action(
        cfg=cfg,
        readiness=readiness,
        difficulty=difficulty,
        mastery=mastery,
        current_score=current_score,
        current_attempts=current_attempts,
        pending=pending,
        criteria_rate=criteria_rate,
        all_mastered=all_mastered,
        current_task_status=current_task_status,
        has_reviews=bool(reviewed),
    )

    return TrajectoryResult(
        mastery=round(mastery, 3),
        difficulty=round(difficulty, 3),
        pace=round(pace, 3),
        readiness=round(readiness, 3),
        action=action,
        reason=reason,
        block_close=block_close,
        block_next_sprint=block_next,
        window_tasks=len(window_task_ids),
        reviewed_in_window=len(window),
        current_task_id=current_id,
        current_attempts=current_attempts,
        current_score=current_score,
        failed_criteria=failed_criteria,
    )


def _mastery(window: Sequence[SubmissionDTO], cfg: TrajectoryConfig) -> float:
    if not window:
        return 0.0
    weights: list[float] = []
    values: list[float] = []
    n = len(window)
    for index, item in enumerate(window, start=1):
        review = item.review
        if review is None:
            continue
        score = normalize_score(review.score) / 10.0
        rate = _criteria_rate(item)
        quality = (1.0 - cfg.criteria_blend) * score + cfg.criteria_blend * rate if rate is not None else score
        weight = cfg.decay ** (n - index)
        weights.append(weight)
        values.append(quality)
    if not weights:
        return 0.0
    return _clamp(sum(w * v for w, v in zip(weights, values)) / sum(weights))


def _difficulty(
        all_subs: Sequence[SubmissionDTO],
        window_task_ids: Sequence[int],
        latest_by_task: dict[int, SubmissionDTO],
        cfg: TrajectoryConfig,
) -> float:
    if not window_task_ids:
        return 0.0
    retry_flags: list[float] = []
    fail_flags: list[float] = []
    coverage: list[float] = []
    for task_id in window_task_ids:
        attempts = sum(1 for item in all_subs if item.task_id == task_id)
        retry_flags.append(1.0 if attempts > 1 else 0.0)
        latest = latest_by_task.get(task_id)
        score = _task_score(latest)
        fail_flags.append(1.0 if score < cfg.low_score else 0.0)
        rate = _criteria_rate(latest)
        if rate is None:
            coverage.append(score / 10.0)
        else:
            coverage.append(rate)
    retry = sum(retry_flags) / len(retry_flags)
    fail = sum(fail_flags) / len(fail_flags)
    closed = sum(coverage) / len(coverage)
    return _clamp(0.4 * retry + 0.3 * fail + 0.3 * (1.0 - closed))


def _pace(
        latest_by_task: dict[int, SubmissionDTO],
        window_task_ids: Sequence[int],
        all_subs: Sequence[SubmissionDTO],
        now: datetime,
        cfg: TrajectoryConfig,
) -> float:
    if not window_task_ids:
        activity = 1.0 if _is_recent(_latest_stamp(all_subs), now, cfg.activity_days) else 0.0
        return _clamp(0.4 * activity)
    done = sum(
        1 for task_id in window_task_ids if _task_score(latest_by_task.get(task_id)) >= cfg.pass_score
    )
    done_ratio = done / len(window_task_ids)
    activity = 1.0 if _is_recent(_latest_stamp(all_subs), now, cfg.activity_days) else 0.0
    return _clamp(0.6 * done_ratio + 0.4 * activity)


def _decide_action(
        cfg: TrajectoryConfig,
        readiness: float,
        difficulty: float,
        mastery: float,
        current_score: int | None,
        current_attempts: int,
        pending: bool,
        criteria_rate: float | None,
        all_mastered: bool,
        current_task_status: str | None,
        has_reviews: bool,
) -> tuple[Action, str, bool, bool]:
    if pending:
        return "wait_review", "Предыдущая сдача ещё на проверке — дождись отчёта.", True, True
    if not has_reviews or current_score is None:
        return "start", "Есть задача без ревью — сдайте решение команде.", True, True

    weak_criteria = criteria_rate is not None and criteria_rate < 0.4
    if current_score < cfg.pass_score:
        if current_attempts < cfg.max_rounds:
            if current_score < cfg.low_score or weak_criteria:
                return (
                    "chat",
                    "Сначала разбери замечания с командой, потом правь код.",
                    True,
                    True,
                )
            return (
                "revise",
                "База есть, но к следующей задаче рано — исправь замечания и сдайте снова.",
                True,
                True,
            )
        return (
            "close_weak",
            "Лимит попыток исчерпан. Закрой задачу как слабую и завершай спринт: "
            "письмо отметит слабый зачёт, оклад не режется.",
            False,
            False,
        )

    status = (current_task_status or "").strip().lower()
    if not status:
        status = "done"
    if status in {"review", "in_progress"}:
        if difficulty >= cfg.d_hard or readiness < cfg.r_next:
            return (
                "close_ok",
                "Эту задачу можно закрыть, но к следующему спринту рано — разбери слабые места.",
                False,
                True,
            )
        return "close_ok", "Команда довольна. Можно закрыть задачу и брать следующий узел.", False, False

    if difficulty >= cfg.d_hard or readiness < cfg.r_next:
        return (
            "next_sprint",
            "Задачи спринта закрыты. Завершай его: письмо отметит тонкую траекторию, "
            "оклад от этого не режется.",
            False,
            False,
        )
    if all_mastered and readiness >= cfg.r_sprint and mastery >= 0.75:
        return "next_sprint", "Траектория устойчивая — можно брать следующий спринт.", False, False
    return "next_task", "Текущий узел закрыт нормально. Бери следующую задачу пути.", False, False


def _latest_reviewed_by_task(reviewed: Sequence[SubmissionDTO]) -> dict[int, SubmissionDTO]:
    latest: dict[int, SubmissionDTO] = {}
    for item in reviewed:
        latest[item.task_id] = item
    return latest


def _latest_task_id(ordered: Sequence[SubmissionDTO]) -> int | None:
    if not ordered:
        return None
    return ordered[-1].task_id


def _task_score(item: SubmissionDTO | None) -> float:
    if item is None or item.review is None:
        return 0.0
    return normalize_score(item.review.score)


def _counts_toward_rounds(item: SubmissionDTO) -> bool:
    if item.status == "pending":
        return False
    if item.review is not None:
        return True
    if item.status == "failed" and item.reviewed_at is not None:
        return True
    return False


def _criteria_rate(item: SubmissionDTO | None) -> float | None:
    if item is None or item.review is None:
        return None
    criteria = item.review.criteria or []
    if not criteria:
        return None
    return sum(1.0 for row in criteria if row.passed) / len(criteria)


def _failed_criteria(item: SubmissionDTO | None) -> list[str]:
    if item is None or item.review is None:
        return []
    return [row.text for row in (item.review.criteria or []) if not row.passed][:8]


def _created_at(item: SubmissionDTO) -> datetime:
    return _as_utc(item.created_at)


def _latest_stamp(items: Iterable[SubmissionDTO]) -> datetime | None:
    stamps: list[datetime] = []
    for item in items:
        stamps.append(_as_utc(item.created_at))
        if item.reviewed_at is not None:
            stamps.append(_as_utc(item.reviewed_at))
    return max(stamps) if stamps else None


def _is_recent(stamp: datetime | None, now: datetime, days: int) -> bool:
    if stamp is None:
        return False
    return (now - stamp) <= timedelta(days=days)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
