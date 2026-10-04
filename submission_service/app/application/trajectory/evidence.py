from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from submission_service.app.application.dto.submission import SubmissionDTO
from submission_service.app.application.drills.models import DRILL_WEIGHT, DrillRun
from submission_service.app.application.trajectory.knowledge import Observation, Opportunity
from submission_service.app.application.trajectory.skills import (
    FALLBACK_SKILL,
    SKILL_BY_ID,
    classify,
    task_profile,
)


CHALLENGE_WEIGHT: dict[str, float] = {"high": 0.8, "medium": 0.5, "low": 0.25}


@dataclass(frozen=True, slots=True)
class EvidenceConfig:
    criterion_weight: float = 1.0
    score_weight: float = 1.0


def criterion_skills(row: Any, text: str) -> list[tuple[str, float]]:
    shares: list[tuple[str, float]] = []
    for item in getattr(row, "skills", None) or []:
        skill_id = str(getattr(item, "skill_id", "") or "").strip()
        try:
            share = float(getattr(item, "share", 0.0))
        except (TypeError, ValueError):
            continue
        if skill_id in SKILL_BY_ID and share > 0.0:
            shares.append((skill_id, share))
    if not shares:
        return classify(text)
    total = sum(share for _, share in shares)
    if total <= 0.0:
        return classify(text)
    return [(skill_id, share / total) for skill_id, share in shares]


def normalize_score(raw: int | float) -> float:
    value = float(raw)
    if value > 10:
        value = value / 10.0
    return max(0.0, min(10.0, value))


def submission_observations(
        item: SubmissionDTO,
        task_description: str | None = None,
        config: EvidenceConfig | None = None,
) -> list[Observation]:
    cfg = config or EvidenceConfig()
    review = item.review
    if review is None:
        return []
    observations: list[Observation] = []
    criteria = list(review.criteria or [])
    for row in criteria:
        text = " ".join(str(row.text or "").split())
        note = " ".join(str(row.note or "").split())
        if not text:
            continue
        for skill_id, share in criterion_skills(row, f"{text}. {note}"):
            observations.append(
                Observation(
                    skill_id=skill_id,
                    outcome=1.0 if row.passed else 0.0,
                    weight=cfg.criterion_weight * share,
                    source="criterion",
                    text=text,
                    note=note,
                )
            )

    for challenge in review.challenges or []:
        text = " ".join(str(challenge.text or "").split())
        if not text:
            continue
        weight = CHALLENGE_WEIGHT.get((challenge.severity or "medium").lower(), 0.5)
        for skill_id, share in classify(text):
            if skill_id == FALLBACK_SKILL:
                continue
            observations.append(
                Observation(
                    skill_id=skill_id,
                    outcome=0.0,
                    weight=weight * share,
                    source="challenge",
                    text=text,
                )
            )

    if not any(obs.source == "criterion" for obs in observations):
        outcome = normalize_score(review.score) / 10.0
        profile = task_profile(task_description) or {FALLBACK_SKILL: 1.0}
        for skill_id, share in profile.items():
            observations.append(
                Observation(
                    skill_id=skill_id,
                    outcome=outcome,
                    weight=cfg.score_weight * share,
                    source="score",
                    text=f"Итоговый балл {int(round(normalize_score(review.score)))}/10",
                )
            )
    return observations


def build_opportunities(
        submissions: Sequence[SubmissionDTO],
        descriptions: dict[int, str] | None = None,
        config: EvidenceConfig | None = None,
) -> list[Opportunity]:
    known = descriptions or {}
    result: list[Opportunity] = []
    for item in submissions:
        observations = submission_observations(item, known.get(item.task_id), config)
        if not observations:
            continue
        result.append(
            Opportunity(
                at=item.reviewed_at or item.created_at,
                task_id=item.task_id,
                submission_id=item.submission_id,
                observations=tuple(observations),
            )
        )
    return result


def drill_opportunities(runs: Sequence[DrillRun]) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    for index, run in enumerate(sorted(runs, key=lambda item: _as_utc(item.at)), start=1):
        if run.total <= 0:
            continue
        opportunities.append(
            Opportunity(
                at=_as_utc(run.at),
                task_id=0,
                submission_id=-index,
                observations=(
                    Observation(
                        skill_id=run.skill_id,
                        outcome=run.outcome,
                        weight=DRILL_WEIGHT,
                        source="drill",
                        text=f"Упражнение: {run.passed}/{run.total}",
                    ),
                ),
            )
        )
    return opportunities


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
