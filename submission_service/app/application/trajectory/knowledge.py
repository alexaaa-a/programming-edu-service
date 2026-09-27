import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Literal, Sequence


SkillStatus = Literal["new", "gap", "learning", "mastered", "fading"]

_EPS = 1e-9
_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True, slots=True)
class BktParams:
    p_init: float = 0.30
    p_learn: float = 0.30
    p_slip: float = 0.05
    p_guess: float = 0.30
    mastery_threshold: float = 0.95
    gap_threshold: float = 0.5
    half_life_days: float = 30.0
    half_life_growth: float = 2.0
    half_life_max_days: float = 365.0
    target_retention: float = 0.8
    prior_strength: float = 4.0
    prior_cap: float = 0.8
    individual_prior: bool = True


@dataclass(frozen=True, slots=True)
class Observation:
    skill_id: str
    outcome: float
    weight: float
    source: str
    text: str = ""
    note: str = ""


@dataclass(frozen=True, slots=True)
class Opportunity:
    at: datetime
    task_id: int
    submission_id: int
    observations: tuple[Observation, ...]


@dataclass(slots=True)
class _Trace:
    p: float
    p0: float
    half_life: float
    last_at: datetime | None = None
    last_growth_day: date | None = None
    evidence: float = 0.0
    opportunities: int = 0
    successes: int = 0
    failures: int = 0
    peak: float = 0.0
    last_outcome: float | None = None


@dataclass(frozen=True, slots=True)
class SkillState:
    skill_id: str
    p_known: float
    p_now: float
    retention: float
    half_life_days: float
    predicted_success: float
    evidence: float
    opportunities: int
    successes: int
    failures: int
    peak: float
    last_practiced_at: datetime | None
    last_outcome: float | None
    status: SkillStatus


@dataclass(frozen=True, slots=True)
class KnowledgeState:
    skills: dict[str, SkillState] = field(default_factory=dict)
    params: BktParams = field(default_factory=BktParams)
    p_prior: float | None = None

    def get(self, skill_id: str) -> SkillState:
        state = self.skills.get(skill_id)
        if state is not None:
            return state
        return empty_state(skill_id, self.params, self.p_prior)

    def practiced(self) -> list[SkillState]:
        return [state for state in self.skills.values() if state.opportunities > 0]


def retention(days: float, half_life_days: float) -> float:
    if days <= 0:
        return 1.0
    return 2.0 ** (-days / max(half_life_days, _EPS))


def forget(p: float, r: float, p_init: float) -> float:
    if p <= p_init:
        return p
    return p_init + (p - p_init) * r


def predict_correct(p: float, params: BktParams) -> float:
    return p * (1.0 - params.p_slip) + (1.0 - p) * params.p_guess


def condition(p: float, observations: Iterable[Observation], params: BktParams) -> float:
    log_known = 0.0
    log_unknown = 0.0
    slip = _clip_prob(params.p_slip)
    guess = _clip_prob(params.p_guess)
    for item in observations:
        c = _clamp(item.outcome)
        w = _clamp(item.weight)
        if w <= 0:
            continue
        log_known += w * (c * math.log(1.0 - slip) + (1.0 - c) * math.log(slip))
        log_unknown += w * (c * math.log(guess) + (1.0 - c) * math.log(1.0 - guess))
    prior = _clip_prob(p)
    log_a = math.log(prior) + log_known
    log_b = math.log(1.0 - prior) + log_unknown
    top = max(log_a, log_b)
    a = math.exp(log_a - top)
    b = math.exp(log_b - top)
    return a / (a + b)


def learn(p: float, strength: float, params: BktParams) -> float:
    return p + (1.0 - p) * params.p_learn * _clamp(strength)


def slip_probability(p: float, params: BktParams) -> float:
    known = p * params.p_slip
    unknown = (1.0 - p) * (1.0 - params.p_guess)
    total = known + unknown
    return known / total if total > 0 else 0.0


def empty_state(skill_id: str, params: BktParams, p_prior: float | None = None) -> SkillState:
    p = params.p_init if p_prior is None else p_prior
    return SkillState(
        skill_id=skill_id,
        p_known=p,
        p_now=p,
        retention=1.0,
        half_life_days=params.half_life_days,
        predicted_success=predict_correct(p, params),
        evidence=0.0,
        opportunities=0,
        successes=0,
        failures=0,
        peak=p,
        last_practiced_at=None,
        last_outcome=None,
        status="new",
    )


class KnowledgeTracer:
    def __init__(self, params: BktParams | None = None) -> None:
        self.params = params or BktParams()
        self._traces: dict[str, _Trace] = {}
        self._success_mass = 0.0
        self._total_mass = 0.0

    def individual_prior(self) -> float:
        cfg = self.params
        if not cfg.individual_prior or self._total_mass <= 0:
            return cfg.p_init
        base = predict_correct(cfg.p_init, cfg)
        rate = (cfg.prior_strength * base + self._success_mass) / (cfg.prior_strength + self._total_mass)
        span = 1.0 - cfg.p_slip - cfg.p_guess
        if span <= 0:
            return cfg.p_init
        return max(0.01, min(cfg.prior_cap, (rate - cfg.p_guess) / span))

    def observe(self, at: datetime, observations: Iterable[Observation]) -> None:
        stamp = _as_utc(at)
        grouped: dict[str, list[Observation]] = {}
        for obs in observations:
            grouped.setdefault(obs.skill_id, []).append(obs)
        prior = self.individual_prior()
        for skill_id, items in grouped.items():
            trace = self._traces.get(skill_id)
            if trace is None:
                trace = _Trace(p=prior, p0=prior, half_life=self.params.half_life_days, peak=prior)
                self._traces[skill_id] = trace
            _step(trace, stamp, items, self.params)
        for obs in observations_list(grouped):
            weight = _clamp(obs.weight)
            self._success_mass += weight * _clamp(obs.outcome)
            self._total_mass += weight

    def predict(self, skill_id: str, at: datetime) -> float:
        return self.state(skill_id, at).predicted_success

    def state(self, skill_id: str, at: datetime) -> SkillState:
        trace = self._traces.get(skill_id)
        if trace is None:
            return empty_state(skill_id, self.params, self.individual_prior())
        return _snapshot(skill_id, trace, _as_utc(at), self.params)

    def snapshot(self, at: datetime) -> KnowledgeState:
        stamp = _as_utc(at)
        return KnowledgeState(
            skills={
                skill_id: _snapshot(skill_id, trace, stamp, self.params)
                for skill_id, trace in self._traces.items()
            },
            params=self.params,
            p_prior=self.individual_prior(),
        )


def observations_list(grouped: dict[str, list[Observation]]) -> list[Observation]:
    return [obs for items in grouped.values() for obs in items]


def trace_knowledge(
        opportunities: Sequence[Opportunity],
        now: datetime,
        params: BktParams | None = None,
        until: datetime | None = None,
) -> KnowledgeState:
    tracer = KnowledgeTracer(params)
    horizon = _as_utc(until or now)
    for item in sorted(opportunities, key=lambda op: _as_utc(op.at)):
        if _as_utc(item.at) > horizon:
            break
        tracer.observe(item.at, item.observations)
    return tracer.snapshot(horizon)


def _snapshot(skill_id: str, trace: _Trace, at: datetime, cfg: BktParams) -> SkillState:
    r = retention(_days_between(trace.last_at, at), trace.half_life)
    p_now = forget(trace.p, r, trace.p0)
    return SkillState(
        skill_id=skill_id,
        p_known=trace.p,
        p_now=p_now,
        retention=r,
        half_life_days=trace.half_life,
        predicted_success=predict_correct(p_now, cfg),
        evidence=trace.evidence,
        opportunities=trace.opportunities,
        successes=trace.successes,
        failures=trace.failures,
        peak=trace.peak,
        last_practiced_at=trace.last_at,
        last_outcome=trace.last_outcome,
        status=_status(p_now, trace, r, cfg),
    )


def _step(trace: _Trace, at: datetime, observations: list[Observation], cfg: BktParams) -> None:
    if trace.last_at is not None:
        r = retention(_days_between(trace.last_at, at), trace.half_life)
        trace.p = forget(trace.p, r, trace.p0)

    weight = sum(_clamp(obs.weight) for obs in observations)
    if weight <= 0:
        return
    outcome = sum(_clamp(obs.outcome) * _clamp(obs.weight) for obs in observations) / weight

    trace.p = condition(trace.p, observations, cfg)
    trace.p = learn(trace.p, min(1.0, weight), cfg)

    success = outcome >= 0.5
    day = at.date()
    if success:
        trace.successes += 1
        spaced = trace.last_growth_day is None or day > trace.last_growth_day
        if spaced and trace.opportunities > 0:
            trace.half_life = min(cfg.half_life_max_days, trace.half_life * cfg.half_life_growth)
            trace.last_growth_day = day
        elif trace.last_growth_day is None:
            trace.last_growth_day = day
    else:
        trace.failures += 1
        trace.half_life = max(cfg.half_life_days, trace.half_life / cfg.half_life_growth)

    trace.evidence += weight
    trace.opportunities += 1
    trace.last_at = at
    trace.last_outcome = outcome
    trace.peak = max(trace.peak, trace.p)


def _status(p_now: float, trace: _Trace, r: float, cfg: BktParams) -> SkillStatus:
    if trace.opportunities == 0:
        return "new"
    if p_now >= cfg.mastery_threshold:
        return "mastered"
    if trace.peak >= cfg.mastery_threshold and r < cfg.target_retention:
        return "fading"
    if p_now < cfg.gap_threshold:
        return "gap"
    return "learning"


def _days_between(start: datetime | None, end: datetime) -> float:
    if start is None:
        return 0.0
    return max(0.0, (_as_utc(end) - _as_utc(start)).total_seconds() / _SECONDS_PER_DAY)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clip_prob(value: float) -> float:
    return min(1.0 - 1e-6, max(1e-6, float(value)))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
