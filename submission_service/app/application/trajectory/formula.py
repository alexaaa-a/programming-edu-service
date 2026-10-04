from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Sequence

from submission_service.app.application.dto.submission import SubmissionDTO
from submission_service.app.application.trajectory.evidence import (
    EvidenceConfig,
    build_opportunities,
    drill_opportunities,
    normalize_score,
    submission_observations,
)
from submission_service.app.application.drills.models import DrillRun
from submission_service.app.application.trajectory.nudge import NudgeSignal, detect_nudge
from submission_service.app.application.trajectory.knowledge import (
    BktParams,
    KnowledgeState,
    Observation,
    SkillState,
    trace_knowledge,
)
from submission_service.app.application.trajectory.planner import (
    OPEN_STATUSES,
    FailureAnalysis,
    Focus,
    NextTask,
    PlannerConfig,
    Recommendation,
    TaskInfo,
    analyze_failures,
    build_recommendations,
    choose_focus,
    choose_next_task,
    expected_success,
)
from submission_service.app.application.trajectory.skills import (
    MENTOR_ACCUSATIVE,
    SKILL_BY_ID,
    task_profile,
)


MODEL_VERSION = "bkt-forgetting/1"

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
    pass_score: int = 8
    low_score: int = 5
    max_rounds: int = 2
    gap_mass_chat: float = 0.5
    activity_half_life_days: float = 2.0
    velocity_days: int = 7
    bkt: BktParams = field(default_factory=BktParams)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    planner: PlannerConfig = field(default_factory=PlannerConfig)

    @property
    def readiness_threshold(self) -> float:
        return max(0.0, min(1.0, (self.pass_score - 1.5) / 9.0))


@dataclass(frozen=True, slots=True)
class SkillView:
    id: str
    title: str
    status: str
    mastery: float
    predicted_success: float
    retention: float
    evidence: float
    opportunities: int
    last_practiced_at: datetime | None


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
    velocity: float = 0.0
    readiness_threshold: float = 0.0
    skills: list[SkillView] = field(default_factory=list)
    focus: Focus | None = None
    recommendations: list[Recommendation] = field(default_factory=list)
    next_task_id: int | None = None
    nudge: NudgeSignal | None = None
    model: str = MODEL_VERSION


def compute_knowledge(
        submissions: Sequence[SubmissionDTO] | None,
        descriptions: dict[int, str] | None = None,
        drill_runs: Sequence[DrillRun] = (),
        now: datetime | None = None,
        config: TrajectoryConfig | None = None,
) -> KnowledgeState:
    cfg = config or TrajectoryConfig()
    stamp = _as_utc(now or datetime.now(tz=timezone.utc))
    ordered = sorted(list(submissions or []), key=_created_at)
    opportunities = build_opportunities(ordered, descriptions or {}, cfg.evidence)
    opportunities.extend(drill_opportunities(drill_runs))
    if not opportunities:
        return KnowledgeState(params=cfg.bkt)
    return trace_knowledge(opportunities, now=stamp, params=cfg.bkt)


def compute_trajectory(
        submissions: Sequence[SubmissionDTO] | None,
        task_id: int | None = None,
        now: datetime | None = None,
        config: TrajectoryConfig | None = None,
        current_task_status: str | None = None,
        tasks: Sequence[TaskInfo] | None = None,
        can_pick_task: bool = False,
        drill_runs: Sequence[DrillRun] = (),
) -> TrajectoryResult:
    cfg = config or TrajectoryConfig()
    stamp = _as_utc(now or datetime.now(tz=timezone.utc))
    items = list(submissions or [])
    task_list = list(tasks or [])
    descriptions = {task.task_id: task.description for task in task_list if task.description}

    if not items:
        open_profile = _open_profile(task_list, exclude=task_id)
        knowledge = (
            trace_knowledge(drill_opportunities(drill_runs), now=stamp, params=cfg.bkt)
            if drill_runs
            else KnowledgeState(params=cfg.bkt)
        )
        current_profile = task_profile(descriptions.get(task_id)) if task_id is not None else {}
        focus = choose_focus(knowledge, None, current_profile, open_profile)
        next_task = choose_next_task(task_list, knowledge, task_id, can_pick=can_pick_task)
        return TrajectoryResult(
            mastery=0.0,
            difficulty=0.0,
            pace=0.0,
            readiness=0.0,
            action="start",
            reason=_with_focus_hint("Ещё нет сдач — возьми первую задачу пути.", focus),
            block_close=True,
            block_next_sprint=True,
            current_task_id=task_id,
            readiness_threshold=round(cfg.readiness_threshold, 3),
            skills=_skill_views(knowledge, focus),
            focus=focus,
            recommendations=build_recommendations(focus, None, knowledge, next_task, cfg.planner),
            next_task_id=next_task.task_id if next_task else None,
        )

    ordered = sorted(items, key=_created_at)
    reviewed = [item for item in ordered if item.review is not None]
    window = reviewed[-cfg.window :] if reviewed else []
    window_task_ids = list(dict.fromkeys(item.task_id for item in window))

    opportunities = build_opportunities(ordered, descriptions, cfg.evidence)
    opportunities.extend(drill_opportunities(drill_runs))
    knowledge = trace_knowledge(opportunities, now=stamp, params=cfg.bkt)

    current_id = task_id if task_id is not None else _latest_task_id(ordered)
    open_profile = _open_profile(task_list, exclude=current_id)
    current_subs = [item for item in ordered if item.task_id == current_id] if current_id is not None else []
    current_reviewed = [item for item in current_subs if item.review is not None]
    latest_current = current_reviewed[-1] if current_reviewed else None
    current_score = (
        int(round(normalize_score(latest_current.review.score)))
        if latest_current is not None and latest_current.review is not None
        else None
    )
    current_attempts = sum(1 for item in current_subs if _counts_toward_rounds(item))
    pending = any(item.status == "pending" for item in current_subs)
    failed_criteria = _failed_criteria(latest_current)

    latest_obs: list[Observation] = []
    failures: FailureAnalysis | None = None
    if latest_current is not None:
        latest_obs = submission_observations(latest_current, descriptions.get(latest_current.task_id), cfg.evidence)
        at = _as_utc(latest_current.reviewed_at or latest_current.created_at)
        prior = trace_knowledge(
            opportunities,
            now=at,
            params=cfg.bkt,
            until=at - timedelta(microseconds=1),
        )
        failures = analyze_failures(latest_obs, prior)

    current_profile = _profile_from_observations(latest_obs) or task_profile(descriptions.get(current_id))
    window_ids = {item.submission_id for item in window}
    window_mix = _profile_from_observations(
        obs for op in opportunities if op.submission_id in window_ids for obs in op.observations
    )

    mastery = _mastery(knowledge)
    readiness = expected_success(window_mix, knowledge) if window_mix else 0.0
    difficulty = 1.0 - expected_success(current_profile or window_mix, knowledge)
    pace = _pace(ordered, stamp, cfg)
    velocity = mastery - _mastery_at(opportunities, knowledge, stamp - timedelta(days=cfg.velocity_days), cfg)

    next_task = choose_next_task(task_list, knowledge, current_id, can_pick=can_pick_task)
    focus = choose_focus(knowledge, failures, current_profile, open_profile)

    action, reason, block_close, block_next = _decide_action(
        cfg=cfg,
        readiness=readiness,
        current_score=current_score,
        current_attempts=current_attempts,
        pending=pending,
        failures=failures,
        focus=focus,
        next_task=next_task,
        current_task_status=current_task_status,
        has_reviews=bool(reviewed),
    )
    fixable = failures if action in {"chat", "revise"} else None
    recommendations = build_recommendations(focus, fixable, knowledge, next_task, cfg.planner)

    return TrajectoryResult(
        mastery=round(mastery, 3),
        difficulty=round(_clamp(difficulty), 3),
        pace=round(pace, 3),
        readiness=round(_clamp(readiness), 3),
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
        velocity=round(velocity, 3),
        readiness_threshold=round(cfg.readiness_threshold, 3),
        skills=_skill_views(knowledge, focus),
        focus=focus,
        recommendations=recommendations,
        next_task_id=next_task.task_id if next_task else None,
        nudge=detect_nudge(ordered, stamp),
    )


def _decide_action(
        cfg: TrajectoryConfig,
        readiness: float,
        current_score: int | None,
        current_attempts: int,
        pending: bool,
        failures: FailureAnalysis | None,
        focus: Focus | None,
        next_task: NextTask | None,
        current_task_status: str | None,
        has_reviews: bool,
) -> tuple[Action, str, bool, bool]:
    if pending:
        return "wait_review", "Предыдущая сдача ещё на проверке — дождись отчёта.", True, True
    if not has_reviews or current_score is None:
        return (
            "start",
            _with_focus_hint("Есть задача без ревью — сдай решение команде.", focus),
            True,
            True,
        )

    thin = readiness < cfg.readiness_threshold
    gap_mass = failures.gap_mass if failures is not None else 0.0
    if current_score < cfg.pass_score:
        if current_attempts < cfg.max_rounds:
            if current_score < cfg.low_score or gap_mass >= cfg.gap_mass_chat:
                return (
                    "chat",
                    _join(
                        "Сначала разбери замечания с командой, потом правь код.",
                        _gap_line(focus),
                    ),
                    True,
                    True,
                )
            return (
                "revise",
                _join(
                    "База есть, но к следующей задаче рано — исправь замечания и сдай снова.",
                    _revise_line(focus),
                ),
                True,
                True,
            )
        return (
            "close_weak",
            _join(
                "Лимит попыток исчерпан. Закрой задачу как слабую и завершай спринт: "
                "письмо отметит слабый зачёт, оклад не режется.",
                f"«{focus.title}» останется в фокусе следующих задач." if focus is not None else "",
            ),
            False,
            False,
        )

    status = (current_task_status or "").strip().lower() or "done"
    if status in {"review", "in_progress"}:
        if thin:
            return (
                "close_ok",
                _join(
                    "Эту задачу можно закрыть, но к следующему спринту рано — разбери слабые места.",
                    _focus_line(focus),
                ),
                False,
                True,
            )
        return "close_ok", "Команда довольна. Можно закрыть задачу и брать следующий узел.", False, False

    if next_task is not None:
        return (
            "next_task",
            _join(
                "Текущий узел закрыт. Бери следующую задачу пути.",
                _focus_line(focus),
            ),
            False,
            thin,
        )
    if thin:
        return (
            "next_sprint",
            _join(
                "Задачи спринта закрыты. Завершай его: письмо отметит тонкую траекторию, "
                "оклад от этого не режется.",
                _focus_line(focus),
            ),
            False,
            True,
        )
    return (
        "next_sprint",
        _join(
            "Траектория устойчивая — можно смело брать следующий спринт.",
            _focus_line(focus),
        ),
        False,
        False,
    )


def _gap_line(focus: Focus | None) -> str:
    if focus is None:
        return ""
    return (
        f"Главный пробел — «{focus.title}»: "
        f"спроси {MENTOR_ACCUSATIVE.get(focus.mentor, focus.mentor_name)}."
    )


def _revise_line(focus: Focus | None) -> str:
    if focus is None:
        return ""
    if focus.kind == "fix":
        return f"По истории «{focus.title}» ты знаешь — похоже на невнимательность, перепроверь."
    if focus.kind == "learn":
        return f"Начни с темы «{focus.title}»: {_lower_first(focus.steps[0])}"
    return f"Начни с «{focus.title}»: {_lower_first(focus.steps[0])}"


def _focus_line(focus: Focus | None) -> str:
    if focus is None:
        return ""
    lead = {
        "fix": "Перепроверь",
        "learn": "Слабее всего",
        "review": "Пора повторить",
        "grow": "Дальше прокачивай",
        "stretch": "Следующий уровень",
        "prepare": "Главное в задаче",
    }[focus.kind]
    return f"{lead}: «{focus.title}»."


def _with_focus_hint(base: str, focus: Focus | None) -> str:
    if focus is None:
        return base
    return _join(base, f"Перед сдачей проверь «{focus.title}»: {_lower_first(focus.steps[0])}")


def _mastery(knowledge: KnowledgeState) -> float:
    practiced = knowledge.practiced()
    total = sum(state.evidence for state in practiced)
    if total <= 0:
        return 0.0
    return _clamp(sum(state.evidence * state.p_now for state in practiced) / total)


def _mastery_at(
        opportunities,
        knowledge: KnowledgeState,
        moment: datetime,
        cfg: TrajectoryConfig,
) -> float:
    practiced = knowledge.practiced()
    total = sum(state.evidence for state in practiced)
    if total <= 0:
        return 0.0
    before = trace_knowledge(opportunities, now=moment, params=cfg.bkt, until=moment)
    return _clamp(
        sum(state.evidence * before.get(state.skill_id).p_now for state in practiced) / total
    )


def _pace(items: Sequence[SubmissionDTO], now: datetime, cfg: TrajectoryConfig) -> float:
    stamp = _latest_stamp(items)
    if stamp is None:
        return 0.0
    days = max(0.0, (now - stamp).total_seconds() / 86400.0)
    return _clamp(2.0 ** (-days / cfg.activity_half_life_days))


def _profile_from_observations(observations: Iterable[Observation]) -> dict[str, float]:
    mix: dict[str, float] = {}
    for obs in observations:
        mix[obs.skill_id] = mix.get(obs.skill_id, 0.0) + obs.weight
    total = sum(mix.values())
    if total <= 0:
        return {}
    return {skill_id: value / total for skill_id, value in mix.items()}


def _open_profile(tasks: Sequence[TaskInfo], exclude: int | None) -> dict[str, float]:
    mix: dict[str, float] = {}
    for task in tasks:
        if task.task_id == exclude or (task.status or "").lower() not in OPEN_STATUSES:
            continue
        for skill_id, share in task_profile(task.description).items():
            mix[skill_id] = mix.get(skill_id, 0.0) + share
    total = sum(mix.values())
    if total <= 0:
        return {}
    return {skill_id: value / total for skill_id, value in mix.items()}


def _skill_views(knowledge: KnowledgeState, focus: Focus | None) -> list[SkillView]:
    states: list[SkillState] = knowledge.practiced()
    if focus is not None and all(state.skill_id != focus.skill_id for state in states):
        states.append(knowledge.get(focus.skill_id))
    states.sort(key=lambda state: (state.opportunities == 0, state.p_now))
    return [
        SkillView(
            id=state.skill_id,
            title=SKILL_BY_ID[state.skill_id].title if state.skill_id in SKILL_BY_ID else state.skill_id,
            status=state.status,
            mastery=round(state.p_now, 3),
            predicted_success=round(state.predicted_success, 3),
            retention=round(state.retention, 3),
            evidence=round(state.evidence, 2),
            opportunities=state.opportunities,
            last_practiced_at=state.last_practiced_at,
        )
        for state in states
    ]


def _latest_task_id(ordered: Sequence[SubmissionDTO]) -> int | None:
    if not ordered:
        return None
    return ordered[-1].task_id


def _counts_toward_rounds(item: SubmissionDTO) -> bool:
    if item.status == "pending":
        return False
    if item.review is not None:
        return True
    if item.status == "failed" and item.reviewed_at is not None:
        return True
    return False


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


def _join(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _pct(value: float) -> int:
    return max(0, min(100, int(round(float(value) * 100))))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "Action",
    "MODEL_VERSION",
    "SkillView",
    "TaskInfo",
    "TrajectoryConfig",
    "TrajectoryResult",
    "compute_trajectory",
    "normalize_score",
]
