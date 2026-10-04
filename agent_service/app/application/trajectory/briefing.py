from dataclasses import dataclass, field

from agent_service.app.application.review.acceptance import is_board_chatter


ACTION_TITLES: dict[str, str] = {
    "start": "взять первую задачу",
    "wait_review": "ждать ревью",
    "revise": "доработать решение",
    "chat": "разобрать замечания с командой",
    "close_ok": "можно закрывать задачу",
    "close_weak": "закрыть как слабую",
    "next_task": "взять следующий узел",
    "hold_sprint": "не открывать следующий спринт",
    "next_sprint": "можно брать следующий спринт",
}


FOCUS_KINDS: dict[str, str] = {
    "fix": "перепроверить",
    "learn": "пробел в знаниях",
    "review": "пора повторить",
    "grow": "прокачать",
    "stretch": "усложнить",
    "prepare": "подготовиться",
}


@dataclass(frozen=True, slots=True)
class TrajectorySnapshot:
    action: str
    reason: str
    mastery: float = 0.0
    difficulty: float = 0.0
    pace: float = 0.0
    readiness: float = 0.0
    current_score: int | None = None
    current_attempts: int = 0
    failed_criteria: list[str] = field(default_factory=list)
    block_next_sprint: bool = False
    block_close: bool = False
    focus_skill: str = ""
    focus_title: str = ""
    focus_kind: str = ""
    focus_why: str = ""
    focus_mastery: float = 0.0
    focus_steps: list[str] = field(default_factory=list)
    focus_mentor: str = ""
    recommendations: list[str] = field(default_factory=list)
    nudge_kind: str = ""
    nudge_task_id: int | None = None
    nudge_hours: int = 0
    nudge_score: int | None = None
    nudge_detail: str = ""


def _pct(value: float) -> int:
    return max(0, min(100, round(float(value) * 100)))


def format_trajectory_briefing(snapshot: TrajectorySnapshot | None) -> str:
    if snapshot is None:
        return ""
    action = (snapshot.action or "").strip()
    step = ACTION_TITLES.get(action, action or "следующий шаг")
    lines = [
        f"Следующий шаг: {step}",
        (snapshot.reason or "").strip(),
        (
            f"M {_pct(snapshot.mastery)}% · D {_pct(snapshot.difficulty)}% · "
            f"P {_pct(snapshot.pace)}% · R {_pct(snapshot.readiness)}%"
        ),
    ]
    if snapshot.current_score is not None:
        lines.append(
            f"Последний балл: {snapshot.current_score}/10, попыток: {snapshot.current_attempts}"
        )
    elif snapshot.current_attempts:
        lines.append(f"Попыток: {snapshot.current_attempts}")
    failed = [
        item.strip()
        for item in snapshot.failed_criteria
        if item and str(item).strip() and not is_board_chatter(str(item))
    ]
    if failed:
        lines.append(f"Не закрыто: {'; '.join(failed[:4])}")
    if snapshot.focus_title:
        kind = FOCUS_KINDS.get(snapshot.focus_kind, "фокус")
        lines.append(
            f"Фокус траектории ({kind}): «{snapshot.focus_title}», владение {_pct(snapshot.focus_mastery)}%."
        )
        if snapshot.focus_why:
            lines.append(snapshot.focus_why.strip())
        steps = [step.strip() for step in snapshot.focus_steps if step and step.strip()]
        if steps:
            lines.append("Шаги: " + " ".join(f"{index}) {step}" for index, step in enumerate(steps[:3], start=1)))
    if snapshot.block_next_sprint:
        lines.append("Следующий спринт пока рано.")
    if snapshot.block_close:
        lines.append("Закрывать задачу ещё рано.")
    return "\n".join(line for line in lines if line)
