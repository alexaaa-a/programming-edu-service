import math
from dataclasses import dataclass, field
from typing import Literal, Sequence

from submission_service.app.application.trajectory.knowledge import (
    KnowledgeState,
    Observation,
    SkillState,
    predict_correct,
    slip_probability,
)
from submission_service.app.application.trajectory.skills import (
    MENTOR_NAMES,
    SKILL_BY_ID,
    SKILLS,
    task_profile,
)


FocusKind = Literal["fix", "learn", "review", "grow", "stretch", "prepare"]
RecommendationKind = Literal["fix", "learn", "review", "practice", "next_task", "stretch"]

OPEN_STATUSES = ("in_progress", "todo")


@dataclass(frozen=True, slots=True)
class TaskInfo:
    task_id: int
    status: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Focus:
    skill_id: str
    title: str
    summary: str
    kind: FocusKind
    status: str
    mastery: float
    predicted_success: float
    why: str
    steps: list[str]
    mentor: str
    mentor_name: str
    ask: str
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Recommendation:
    kind: RecommendationKind
    title: str
    detail: str
    skill_id: str | None = None
    task_id: int | None = None
    mentor: str | None = None
    ask: str | None = None


@dataclass(frozen=True, slots=True)
class NextTask:
    task_id: int
    utility: float
    predicted_success: float
    skills: list[str]
    in_progress: bool


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    failed: list[Observation]
    gap_mass: float
    slip_by_skill: dict[str, float]


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    max_recommendations: int = 5
    max_fix: int = 3


def analyze_failures(
        latest: Sequence[Observation],
        prior: KnowledgeState,
) -> FailureAnalysis:
    criteria = [obs for obs in latest if obs.source == "criterion"]
    failed = [obs for obs in criteria if obs.outcome < 0.5]
    slips: dict[str, float] = {}
    for obs in failed:
        if obs.skill_id not in slips:
            slips[obs.skill_id] = slip_probability(prior.get(obs.skill_id).p_now, prior.params)
    total = sum(obs.weight for obs in criteria)
    if total <= 0:
        return FailureAnalysis(failed=failed, gap_mass=0.0, slip_by_skill=slips)
    gap = sum(obs.weight * (1.0 - slips[obs.skill_id]) for obs in failed)
    return FailureAnalysis(failed=failed, gap_mass=gap / total, slip_by_skill=slips)


def expected_success(profile: dict[str, float], knowledge: KnowledgeState) -> float:
    if not profile:
        return predict_correct(knowledge.params.p_init, knowledge.params)
    return sum(share * knowledge.get(skill_id).predicted_success for skill_id, share in profile.items())


def learning_gain(profile: dict[str, float], knowledge: KnowledgeState) -> float:
    return sum(
        share * (1.0 - knowledge.get(skill_id).p_now) * knowledge.params.p_learn
        for skill_id, share in profile.items()
    )


def realized_gain(profile: dict[str, float], knowledge: KnowledgeState) -> float:
    return learning_gain(profile, knowledge) * expected_success(profile, knowledge)


def choose_next_task(
        tasks: Sequence[TaskInfo] | None,
        knowledge: KnowledgeState,
        current_task_id: int | None,
) -> NextTask | None:
    candidates = [
        task
        for task in (tasks or [])
        if task.task_id != current_task_id and (task.status or "").lower() in OPEN_STATUSES
    ]
    if not candidates:
        return None
    started = [task for task in candidates if (task.status or "").lower() == "in_progress"]
    pool = started or candidates
    best: NextTask | None = None
    for task in pool:
        profile = task_profile(task.description) or {"requirements": 1.0}
        success = expected_success(profile, knowledge)
        utility = realized_gain(profile, knowledge)
        ranked = sorted(profile.items(), key=lambda item: -item[1])
        option = NextTask(
            task_id=task.task_id,
            utility=utility,
            predicted_success=success,
            skills=[skill_id for skill_id, _ in ranked[:3]],
            in_progress=bool(started),
        )
        if best is None or option.utility > best.utility + 1e-12:
            best = option
    return best


def choose_focus(
        knowledge: KnowledgeState,
        failures: FailureAnalysis | None,
        current_profile: dict[str, float],
        open_profile: dict[str, float],
) -> Focus | None:
    params = knowledge.params

    if failures is not None and failures.failed:
        contribution: dict[str, tuple[float, float]] = {}
        for obs in failures.failed:
            gap, mass = contribution.get(obs.skill_id, (0.0, 0.0))
            slip_share = failures.slip_by_skill.get(obs.skill_id, 0.0)
            contribution[obs.skill_id] = (gap + obs.weight * (1.0 - slip_share), mass + obs.weight)
        skill_id = max(
            contribution,
            key=lambda sid: (contribution[sid][0], contribution[sid][1], -_index(sid)),
        )
        state = knowledge.get(skill_id)
        slip = failures.slip_by_skill.get(skill_id, 0.0)
        evidence = [
            _criterion_line(obs) for obs in failures.failed if obs.skill_id == skill_id
        ]
        if slip >= 0.5:
            why = (
                "Тема тебе знакома — похоже, просто не заметил. "
                "Перечитай шаги ниже и сверь код построчно."
            )
            return _focus(skill_id, "fix", state, why, evidence)
        why = "Тема пока не закрыта — без разбора она всплывёт и в следующей задаче."
        return _focus(skill_id, "learn", state, why, evidence)

    fading = [state for state in knowledge.practiced() if state.status == "fading"]
    if fading:
        state = min(fading, key=lambda item: (item.retention, _index(item.skill_id)))
        days = _days_ago(state)
        why = (
            f"Ты это уже умел, но не трогал {days} дн. — понемногу забывается. "
            "Полчаса практики сейчас дешевле, чем учить заново."
        )
        return _focus(state.skill_id, "review", state, why)

    growing = [state for state in knowledge.practiced() if state.p_now < params.mastery_threshold]
    if growing:
        def utility(item: SkillState) -> float:
            relevance = 1.0 + current_profile.get(item.skill_id, 0.0) + open_profile.get(item.skill_id, 0.0)
            return realized_gain({item.skill_id: 1.0}, knowledge) * relevance

        state = max(growing, key=lambda item: (utility(item), -_index(item.skill_id)))
        why = (
            "Здесь граница твоих умений — ровно то, что стоит потренировать сейчас. "
            "Одна задача тут даст больше роста, чем где угодно ещё."
        )
        return _focus(state.skill_id, "grow", state, why)

    practiced = knowledge.practiced()
    if practiced:
        fresh = [
            skill_id
            for skill_id, _ in sorted(open_profile.items(), key=lambda item: -item[1])
            if knowledge.get(skill_id).opportunities == 0
        ]
        if fresh:
            skill_id = fresh[0]
            state = knowledge.get(skill_id)
            why = (
                "Все встреченные навыки освоены. В открытых задачах есть навык, "
                "который ты ещё не показывал на ревью, — начни с него."
            )
            return _focus(skill_id, "stretch", state, why)
        state = min(practiced, key=lambda item: (item.evidence, _index(item.skill_id)))
        why = (
            f"Всё, что встречалось, ты закрыл. «{SKILL_BY_ID[state.skill_id].title}» "
            "подтверждён меньше остальных — самое время усложнить."
        )
        return _focus(state.skill_id, "stretch", state, why)

    profile = current_profile or open_profile
    if profile:
        skill_id = max(profile.items(), key=lambda item: (item[1], -_index(item[0])))[0]
        state = knowledge.get(skill_id)
        why = (
            "Ревью по этой задаче ещё не было. Судя по брифу, вот на чём здесь всё "
            "держится — пройдись по шагам до сдачи."
        )
        return _focus(skill_id, "prepare", state, why)
    return None


def build_recommendations(
        focus: Focus | None,
        failures: FailureAnalysis | None,
        knowledge: KnowledgeState,
        next_task: NextTask | None,
        cfg: PlannerConfig | None = None,
) -> list[Recommendation]:
    config = cfg or PlannerConfig()
    items: list[Recommendation] = []

    if failures is not None:
        seen: set[str] = set()
        for obs in failures.failed:
            if obs.text in seen:
                continue
            seen.add(obs.text)
            skill = SKILL_BY_ID.get(obs.skill_id)
            detail = obs.note or (f"Навык: {skill.title}. {skill.summary}" if skill else "")
            items.append(
                Recommendation(
                    kind="fix",
                    title=f"Исправь: {obs.text}",
                    detail=detail,
                    skill_id=obs.skill_id,
                )
            )
            if len(seen) >= config.max_fix:
                break

    if focus is not None:
        kind: RecommendationKind = {
            "fix": "fix",
            "learn": "learn",
            "review": "review",
            "grow": "practice",
            "stretch": "stretch",
            "prepare": "practice",
        }[focus.kind]
        title = {
            "fix": f"Перепроверь навык «{focus.title}»",
            "learn": f"Разбери тему «{focus.title}» с командой",
            "review": f"Повтори навык «{focus.title}»",
            "grow": f"Прокачай навык «{focus.title}»",
            "stretch": f"Усложни: «{focus.title}»",
            "prepare": f"Перед сдачей проверь «{focus.title}»",
        }[focus.kind]
        skill = SKILL_BY_ID[focus.skill_id]
        if focus.kind == "stretch":
            detail = skill.stretch
        elif focus.kind in {"learn", "fix"}:
            detail = f"Готовый вопрос: «{focus.ask}»"
        else:
            detail = focus.steps[0]
        items.append(
            Recommendation(
                kind=kind,
                title=title,
                detail=detail,
                skill_id=focus.skill_id,
                mentor=focus.mentor,
                ask=focus.ask,
            )
        )

    focus_id = focus.skill_id if focus is not None else None
    fading = sorted(
        (state for state in knowledge.practiced() if state.status == "fading" and state.skill_id != focus_id),
        key=lambda item: item.retention,
    )
    for state in fading[:1]:
        skill = SKILL_BY_ID[state.skill_id]
        items.append(
            Recommendation(
                kind="review",
                title=f"Освежи «{skill.title}»",
                detail=(
                    f"Не встречался {_days_ago(state)} дн., удержание {_pct(state.retention)}%. "
                    f"В ближайшей задаче: {_lower_first(skill.steps[0])}"
                ),
                skill_id=state.skill_id,
                mentor=skill.mentor,
            )
        )

    if next_task is not None:
        names = [SKILL_BY_ID[sid].title for sid in next_task.skills if sid in SKILL_BY_ID]
        if next_task.in_progress:
            detail = (
                "Она уже в работе — доведи её до ревью, прежде чем брать новую: "
                "незавершённые задачи размывают фокус."
            )
        else:
            detail = (
                f"Тренирует: {', '.join(names[:2]) or 'логику задачи'}. "
                f"Ожидаемый успех {_pct(next_task.predicted_success)}% — "
                "среди открытых задач она даст наибольший прирост навыков."
            )
        items.append(
            Recommendation(
                kind="next_task",
                title="Следующая задача",
                detail=detail,
                task_id=next_task.task_id,
                skill_id=next_task.skills[0] if next_task.skills else None,
            )
        )

    return items[: config.max_recommendations]


def _focus(
        skill_id: str,
        kind: FocusKind,
        state: SkillState,
        why: str,
        evidence: list[str] | None = None,
) -> Focus:
    skill = SKILL_BY_ID[skill_id]
    steps = list(skill.steps)
    if kind == "stretch":
        steps = [skill.stretch, *skill.steps[:1]]
    return Focus(
        skill_id=skill_id,
        title=skill.title,
        summary=skill.summary,
        kind=kind,
        status=state.status,
        mastery=round(state.p_now, 3),
        predicted_success=round(state.predicted_success, 3),
        why=why,
        steps=steps,
        mentor=skill.mentor,
        mentor_name=MENTOR_NAMES.get(skill.mentor, skill.mentor),
        ask=skill.ask,
        evidence=list(dict.fromkeys(evidence or []))[:3],
    )


def _criterion_line(obs: Observation) -> str:
    if obs.note:
        return f"{obs.text} — {obs.note}"
    return obs.text


def _days_ago(state: SkillState) -> int:
    return max(0, int(round(-math.log2(max(state.retention, 1e-9)) * state.half_life_days)))


def _pct(value: float) -> int:
    return max(0, min(100, int(round(float(value) * 100))))


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _index(skill_id: str) -> int:
    for index, skill in enumerate(SKILLS):
        if skill.id == skill_id:
            return index
    return len(SKILLS)
