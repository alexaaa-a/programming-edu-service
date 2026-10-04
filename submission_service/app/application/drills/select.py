from datetime import datetime, timedelta, timezone
from typing import Sequence

from submission_service.app.application.drills.bank import DRILLS_BY_SKILL
from submission_service.app.application.drills.models import Drill, DrillPick, DrillRun
from submission_service.app.application.trajectory.knowledge import KnowledgeState, SkillState
from submission_service.app.application.trajectory.skills import SKILL_BY_ID


SKILL_COOLDOWN_HOURS = 20
DRILL_COOLDOWN_DAYS = 7


def choose_drill(
        knowledge: KnowledgeState,
        history: Sequence[DrillRun] = (),
        now: datetime | None = None,
) -> DrillPick | None:
    stamp = _as_utc(now or datetime.now(tz=timezone.utc))
    runs = sorted(history, key=lambda item: _as_utc(item.at))
    recent_skills = {
        run.skill_id
        for run in runs
        if run.ok and _as_utc(run.at) > stamp - timedelta(hours=SKILL_COOLDOWN_HOURS)
    }

    for state, kind in _candidates(knowledge):
        if state.skill_id in recent_skills:
            continue
        drill = _pick_drill(state.skill_id, runs, stamp)
        if drill is None:
            continue
        days = _days_since(state, stamp)
        return DrillPick(
            drill=drill,
            skill_id=state.skill_id,
            skill_title=_title(state.skill_id),
            kind=kind,
            reason=_reason(kind, _title(state.skill_id), days, state),
            days_since=days,
            retention=state.retention,
        )
    return None


def _candidates(knowledge: KnowledgeState) -> list[tuple[SkillState, str]]:
    practiced = knowledge.practiced()
    fading = sorted(
        (state for state in practiced if state.status == "fading"),
        key=lambda item: item.retention,
    )
    gaps = sorted(
        (state for state in practiced if state.status == "gap"),
        key=lambda item: item.p_now,
    )
    return [(state, "review") for state in fading] + [(state, "gap") for state in gaps]


def _pick_drill(skill_id: str, runs: Sequence[DrillRun], now: datetime) -> Drill | None:
    drills = DRILLS_BY_SKILL.get(skill_id, ())
    if not drills:
        return None
    last_seen: dict[str, datetime] = {}
    for run in runs:
        last_seen[run.drill_id] = _as_utc(run.at)

    fresh = [drill for drill in drills if drill.id not in last_seen]
    if fresh:
        return fresh[0]
    cutoff = now - timedelta(days=DRILL_COOLDOWN_DAYS)
    rested = [drill for drill in drills if last_seen[drill.id] <= cutoff]
    if rested:
        return min(rested, key=lambda drill: last_seen[drill.id])
    return min(drills, key=lambda drill: last_seen[drill.id])


def _reason(kind: str, title: str, days: int, state: SkillState) -> str:
    if kind == "review":
        when = f"{days} дн. назад" if days > 0 else "недавно"
        return (
            f"«{title}» ты уже показывал, последний раз {when}. "
            "По модели тема заходит в забывание — пять минут сейчас дешевле, чем разбираться заново."
        )
    return (
        f"«{title}» пока не закрыт: на ревью он чаще падал, чем проходил. "
        "Маленькое упражнение без оценки — чтобы попробовать ещё раз."
    )


def _title(skill_id: str) -> str:
    skill = SKILL_BY_ID.get(skill_id)
    return skill.title if skill is not None else skill_id


def _days_since(state: SkillState, now: datetime) -> int:
    if state.last_practiced_at is None:
        return 0
    delta = now - _as_utc(state.last_practiced_at)
    return max(0, int(delta.total_seconds() // 86400))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
