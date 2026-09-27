from dataclasses import dataclass
from typing import Iterable, Protocol


class _Closeable(Protocol):
    close_quality: str | None


class _Trajectory(Protocol):
    block_next_sprint: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SprintHoldDecision:
    hold: bool
    reason: str
    code: str
    weak_count: int
    task_count: int


def evaluate_sprint_hold(
        tasks: Iterable[_Closeable] | None,
        trajectory: _Trajectory | None = None,
) -> SprintHoldDecision:
    items = list(tasks or [])
    task_count = len(items)
    weak_count = sum(1 for item in items if (item.close_quality or "") == "weak")

    if trajectory is None:
        return SprintHoldDecision(
            hold=True,
            reason=(
                "Не удалось получить траекторию обучения — "
                "новый спринт пока не открываем. Повторите позже или откройте осознанно."
            ),
            code="trajectory_unavailable",
            weak_count=weak_count,
            task_count=task_count,
        )

    if trajectory.block_next_sprint:
        return SprintHoldDecision(
            hold=True,
            reason=trajectory.reason
            or "Траектория ещё тяжёлая — рано открывать следующий спринт.",
            code="trajectory",
            weak_count=weak_count,
            task_count=task_count,
        )
    return SprintHoldDecision(
        hold=False,
        reason="",
        code="ok",
        weak_count=weak_count,
        task_count=task_count,
    )
