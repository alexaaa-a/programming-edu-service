import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from submission_service.app.application.dto.submission import SubmissionDTO


PASS_SCORE = 8
SILENCE_HOURS = 6
SILENCE_LIMIT_HOURS = 72
REPEAT_SIMILARITY = 0.97

COMMENT = re.compile(r"#.*$|//.*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class NudgeSignal:
    kind: str
    task_id: int
    hours_since: int
    score: int | None = None
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "task_id": self.task_id,
            "hours_since": self.hours_since,
            "score": self.score,
            "detail": self.detail,
        }


def detect_nudge(
        submissions: Sequence[SubmissionDTO] | None,
        now: datetime | None = None,
) -> NudgeSignal | None:
    rows = sorted(
        [item for item in (submissions or [])],
        key=lambda item: _as_utc(item.created_at),
    )
    if not rows:
        return None
    stamp = _as_utc(now or datetime.now(tz=timezone.utc))
    latest = rows[-1]

    repeat = _repeat_signal(rows, latest, stamp)
    if repeat is not None:
        return repeat
    return _silence_signal(latest, stamp)


def _repeat_signal(
        rows: Sequence[SubmissionDTO],
        latest: SubmissionDTO,
        now: datetime,
) -> NudgeSignal | None:
    previous = [
        item
        for item in rows[:-1]
        if item.task_id == latest.task_id and item.submission_id != latest.submission_id
    ]
    if not previous:
        return None
    before = previous[-1]
    if similarity(before.code, latest.code) < REPEAT_SIMILARITY:
        return None
    score = before.review.score if before.review is not None else None
    return NudgeSignal(
        kind="repeat",
        task_id=latest.task_id,
        hours_since=_hours(latest.created_at, now),
        score=_as_ten(score),
        detail="вторая сдача почти не отличается от первой",
    )


def _silence_signal(latest: SubmissionDTO, now: datetime) -> NudgeSignal | None:
    review = latest.review
    if review is None:
        return None
    score = _as_ten(review.score)
    if score is None or score >= PASS_SCORE:
        return None
    since = latest.reviewed_at or latest.created_at
    hours = _hours(since, now)
    if hours < SILENCE_HOURS or hours > SILENCE_LIMIT_HOURS:
        return None
    return NudgeSignal(
        kind="silence",
        task_id=latest.task_id,
        hours_since=hours,
        score=score,
        detail=f"после отказа прошло {hours} ч, новой сдачи нет",
    )


def similarity(first: str, second: str) -> float:
    left = _normalize(first)
    right = _normalize(second)
    if not left or not right:
        return 1.0 if left == right else 0.0
    if left == right:
        return 1.0
    left_lines = _lines(left)
    right_lines = _lines(right)
    common = 0
    pool = list(right_lines)
    for line in left_lines:
        if line in pool:
            pool.remove(line)
            common += 1
    longest = max(len(left_lines), len(right_lines))
    return common / longest if longest else 0.0


def _normalize(code: str) -> str:
    without_comments = COMMENT.sub("", code or "")
    return "\n".join(
        " ".join(line.split()) for line in without_comments.splitlines() if line.strip()
    )


def _lines(code: str) -> list[str]:
    return [line for line in code.splitlines() if line]


def _hours(value: datetime | None, now: datetime) -> int:
    if value is None:
        return 0
    delta = now - _as_utc(value)
    return max(0, int(delta.total_seconds() // 3600))


def _as_ten(score: int | float | None) -> int | None:
    if score is None:
        return None
    value = float(score)
    if value > 10:
        value = value / 10.0
    return int(round(max(0.0, min(10.0, value))))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
