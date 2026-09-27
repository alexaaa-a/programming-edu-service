import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from submission_service.app.application.trajectory.knowledge import (
    BktParams,
    KnowledgeTracer,
    Observation,
)


@dataclass(frozen=True, slots=True)
class SimConfig:
    students: int = 200
    tasks_per_student: int = 24
    skills: int = 8
    seed: int = 7
    true_half_life_days: float = 20.0
    long_break_probability: float = 0.12
    focus_after_tasks: int = 4


@dataclass(frozen=True, slots=True)
class PredictorScore:
    name: str
    auc: float
    brier: float
    log_loss: float
    n: int


@dataclass(frozen=True, slots=True)
class FocusScore:
    name: str
    hit_rate: float
    regret: float
    n: int


@dataclass(frozen=True, slots=True)
class SimReport:
    predictors: list[PredictorScore] = field(default_factory=list)
    focus: list[FocusScore] = field(default_factory=list)

    def predictor(self, name: str) -> PredictorScore:
        return next(item for item in self.predictors if item.name == name)

    def focus_by(self, name: str) -> FocusScore:
        return next(item for item in self.focus if item.name == name)

    def as_markdown(self) -> str:
        lines = [
            "| Предсказатель | AUC ↑ | Brier ↓ | LogLoss ↓ |",
            "|---|---|---|---|",
        ]
        for item in self.predictors:
            lines.append(f"| {item.name} | {item.auc:.3f} | {item.brier:.3f} | {item.log_loss:.3f} |")
        lines.append("")
        lines.append("| Выбор фокуса | Попадание в самый слабый навык ↑ | Сожаление ↓ |")
        lines.append("|---|---|---|")
        for item in self.focus:
            lines.append(f"| {item.name} | {item.hit_rate:.1%} | {item.regret:.3f} |")
        return "\n".join(lines)


_PREDICTORS = ("bkt_forgetting", "bkt", "skill_mean", "student_mean", "legacy")


def simulate(config: SimConfig | None = None) -> SimReport:
    cfg = config or SimConfig()
    rng = random.Random(cfg.seed)
    skills = [f"s{index}" for index in range(cfg.skills)]
    beta = {skill: rng.gauss(-0.3, 0.8) for skill in skills}
    gamma = {skill: rng.uniform(0.3, 0.7) for skill in skills}
    popularity = {skill: rng.uniform(0.5, 2.0) for skill in skills}

    predictions: dict[str, list[float]] = {name: [] for name in _PREDICTORS}
    outcomes: list[int] = []
    focus_hits: dict[str, list[float]] = {"bkt_forgetting": [], "last_failure": [], "random": []}
    focus_regret: dict[str, list[float]] = {"bkt_forgetting": [], "last_failure": [], "random": []}

    no_forgetting = BktParams(half_life_days=1e9, half_life_max_days=1e9)

    for _ in range(cfg.students):
        theta = rng.gauss(0.0, 0.8)
        practice = {skill: 0.0 for skill in skills}
        tracer = KnowledgeTracer(BktParams())
        tracer_plain = KnowledgeTracer(no_forgetting)
        skill_counts: dict[str, list[int]] = {skill: [0, 0] for skill in skills}
        student_counts = [0, 0]
        legacy_scores: list[float] = []
        last_failure: dict[str, datetime] = {}
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        last = now

        for task_index in range(cfg.tasks_per_student):
            if rng.random() < cfg.long_break_probability:
                gap = rng.uniform(10.0, 30.0)
            else:
                gap = rng.expovariate(1.0 / 1.2) + 0.05
            now = now + timedelta(days=gap)
            decay = 2.0 ** (-gap / cfg.true_half_life_days)
            for skill in skills:
                practice[skill] *= decay

            def true_p(skill: str) -> float:
                return _sigmoid(theta + beta[skill] + gamma[skill] * practice[skill])

            practiced = [skill for skill in skills if skill_counts[skill][0] + skill_counts[skill][1] > 0]
            if task_index >= cfg.focus_after_tasks and len(practiced) >= 2:
                truth = {skill: true_p(skill) for skill in practiced}
                weakest = min(truth.values())
                picks = {
                    "bkt_forgetting": min(practiced, key=lambda s: tracer.predict(s, now)),
                    "last_failure": max(
                        practiced,
                        key=lambda s: last_failure.get(s, datetime.min.replace(tzinfo=timezone.utc)),
                    ),
                    "random": rng.choice(practiced),
                }
                for name, pick in picks.items():
                    focus_hits[name].append(1.0 if truth[pick] <= weakest + 1e-12 else 0.0)
                    focus_regret[name].append(truth[pick] - weakest)

            task_skills = _sample_skills(rng, skills, popularity, rng.randint(1, 3))
            criteria = [rng.choice(task_skills) for _ in range(rng.randint(2, 4))]
            legacy_prior = _legacy_mastery(legacy_scores)
            observations: list[Observation] = []
            passed = 0
            for skill in criteria:
                outcome = 1 if rng.random() < true_p(skill) else 0
                ok, fail = skill_counts[skill]
                predictions["bkt_forgetting"].append(tracer.predict(skill, now))
                predictions["bkt"].append(tracer_plain.predict(skill, now))
                predictions["skill_mean"].append((ok + 1) / (ok + fail + 2))
                predictions["student_mean"].append((student_counts[0] + 1) / (sum(student_counts) + 2))
                predictions["legacy"].append(legacy_prior)
                outcomes.append(outcome)
                observations.append(
                    Observation(skill_id=skill, outcome=float(outcome), weight=1.0, source="criterion")
                )
                passed += outcome
                if outcome:
                    skill_counts[skill][0] += 1
                    student_counts[0] += 1
                else:
                    skill_counts[skill][1] += 1
                    student_counts[1] += 1
                    last_failure[skill] = now

            tracer.observe(now, observations)
            tracer_plain.observe(now, observations)
            rate = passed / len(criteria)
            score = 1 + round(9 * rate)
            legacy_scores.append(0.7 * score / 10.0 + 0.3 * rate)
            for skill in set(task_skills):
                practice[skill] += 1.0
            last = now

    del last
    report = SimReport(
        predictors=[
            PredictorScore(
                name=name,
                auc=_auc(predictions[name], outcomes),
                brier=_brier(predictions[name], outcomes),
                log_loss=_log_loss(predictions[name], outcomes),
                n=len(outcomes),
            )
            for name in _PREDICTORS
        ],
        focus=[
            FocusScore(
                name=name,
                hit_rate=sum(focus_hits[name]) / max(1, len(focus_hits[name])),
                regret=sum(focus_regret[name]) / max(1, len(focus_regret[name])),
                n=len(focus_hits[name]),
            )
            for name in focus_hits
        ],
    )
    return report


def _legacy_mastery(scores: list[float], window: int = 8, decay: float = 0.7) -> float:
    recent = scores[-window:]
    if not recent:
        return 0.5
    n = len(recent)
    weights = [decay ** (n - index) for index in range(1, n + 1)]
    return sum(w * v for w, v in zip(weights, recent)) / sum(weights)


def _sample_skills(rng: random.Random, skills: list[str], popularity: dict[str, float], count: int) -> list[str]:
    pool = list(skills)
    chosen: list[str] = []
    for _ in range(min(count, len(pool))):
        total = sum(popularity[skill] for skill in pool)
        mark = rng.uniform(0.0, total)
        acc = 0.0
        for skill in pool:
            acc += popularity[skill]
            if acc >= mark:
                chosen.append(skill)
                pool.remove(skill)
                break
    return chosen


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _auc(scores: list[float], labels: list[int]) -> float:
    pairs = sorted(zip(scores, labels), key=lambda item: item[0])
    ranks = [0.0] * len(pairs)
    index = 0
    while index < len(pairs):
        end = index
        while end + 1 < len(pairs) and pairs[end + 1][0] == pairs[index][0]:
            end += 1
        rank = (index + end) / 2.0 + 1.0
        for pos in range(index, end + 1):
            ranks[pos] = rank
        index = end + 1
    positives = sum(label for _, label in pairs)
    negatives = len(pairs) - positives
    if positives == 0 or negatives == 0:
        return 0.5
    rank_sum = sum(rank for rank, (_, label) in zip(ranks, pairs) if label == 1)
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _brier(scores: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(scores, labels)) / max(1, len(labels))


def _log_loss(scores: list[float], labels: list[int]) -> float:
    total = 0.0
    for p, y in zip(scores, labels):
        q = min(1.0 - 1e-6, max(1e-6, p))
        total -= y * math.log(q) + (1 - y) * math.log(1.0 - q)
    return total / max(1, len(labels))


def summarize(config: SimConfig | None = None, seeds: int = 10) -> str:
    base = config or SimConfig()
    runs = [
        simulate(
            SimConfig(
                students=base.students,
                tasks_per_student=base.tasks_per_student,
                skills=base.skills,
                seed=seed,
                true_half_life_days=base.true_half_life_days,
                long_break_probability=base.long_break_probability,
                focus_after_tasks=base.focus_after_tasks,
            )
        )
        for seed in range(1, seeds + 1)
    ]
    lines = [
        f"Сидов: {seeds}, студентов в прогоне: {base.students}, задач на студента: {base.tasks_per_student}.",
        "",
        "| Предсказатель | AUC ↑ | Brier ↓ | LogLoss ↓ |",
        "|---|---|---|---|",
    ]
    for name in _PREDICTORS:
        auc = [run.predictor(name).auc for run in runs]
        brier = [run.predictor(name).brier for run in runs]
        loss = [run.predictor(name).log_loss for run in runs]
        lines.append(f"| {name} | {_fmt(auc)} | {_fmt(brier)} | {_fmt(loss)} |")
    lines.append("")
    lines.append("| Выбор фокуса | Попадание в самый слабый навык ↑ | Сожаление ↓ |")
    lines.append("|---|---|---|")
    for item in runs[0].focus:
        hits = [run.focus_by(item.name).hit_rate for run in runs]
        regret = [run.focus_by(item.name).regret for run in runs]
        lines.append(f"| {item.name} | {_fmt(hits)} | {_fmt(regret)} |")
    return "\n".join(lines)


def _fmt(values: list[float]) -> str:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return f"{mean:.3f}"
    std = math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
    return f"{mean:.3f} ± {std:.3f}"


if __name__ == "__main__":
    print(summarize())
