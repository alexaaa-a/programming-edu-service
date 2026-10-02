from typing import Mapping, Sequence

from submission_service.app.application.decisions.questions import (
    Answers,
    Choice,
    Question,
)
from submission_service.app.application.trajectory.skills import SKILLS, SKILL_BY_ID


MAX_TAGGED_CRITERIA = 12
MAX_SKILLS_PER_CRITERION = 2
MIN_SECOND_SHARE = 0.20


def skill_options() -> dict[str, str]:
    return {skill.id: f"{skill.title}. {skill.summary}" for skill in SKILLS}


def tagging_questions(criteria: Sequence[str]) -> list[Question]:
    options = skill_options()
    return [
        Choice(
            name=f"criterion_{index}",
            instructions=(
                f"Какой навык проверяет критерий #{index} из списка criteria?"
            ),
            options=options,
        )
        for index in range(min(len(criteria), MAX_TAGGED_CRITERIA))
    ]


def tagging_state(
        criteria: Sequence[str],
        task_title: str | None = None,
        task_description: str | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "criteria": {
            f"#{index}": text[:400]
            for index, text in enumerate(criteria[:MAX_TAGGED_CRITERIA])
        }
    }
    if task_title:
        state["task_title"] = str(task_title)[:200]
    if task_description:
        state["task_description"] = str(task_description)[:1000]
    return state


def read_tags(
        answers: Answers,
        count: int,
        min_confidence: float,
) -> dict[int, list[tuple[str, float]]]:
    tags: dict[int, list[tuple[str, float]]] = {}
    if not answers:
        return tags
    for index in range(min(count, MAX_TAGGED_CRITERIA)):
        answer = answers.choice(f"criterion_{index}", min_confidence=min_confidence)
        if answer is None:
            continue
        shares = _top_shares(answer.value, answer.probabilities)
        if shares:
            tags[index] = shares
    return tags


def _top_shares(
        value: str,
        probabilities: Mapping[str, float],
) -> list[tuple[str, float]]:
    known = {
        skill_id: float(probability)
        for skill_id, probability in (probabilities or {}).items()
        if skill_id in SKILL_BY_ID and float(probability) > 0.0
    }
    if value not in SKILL_BY_ID:
        return []
    if not known:
        return [(value, 1.0)]
    ordered = sorted(known.items(), key=lambda item: item[1], reverse=True)
    top = [item for item in ordered[:MAX_SKILLS_PER_CRITERION]]
    total = sum(probability for _, probability in top)
    if total <= 0.0:
        return [(value, 1.0)]
    shares = [(skill_id, probability / total) for skill_id, probability in top]
    shares = [item for item in shares if item[1] >= MIN_SECOND_SHARE or item is shares[0]]
    total = sum(share for _, share in shares)
    return [(skill_id, share / total) for skill_id, share in shares]
