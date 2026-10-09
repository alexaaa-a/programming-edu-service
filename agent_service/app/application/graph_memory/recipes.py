from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from agent_service.app.application.decisions.questions import Answers, Choice, Question
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    PREFERS,
    STRUGGLES_WITH,
    WORKED_ON,
)


class ReadIntent(str, Enum):
    STUDENT_NOW = "student_now"
    TASK_CONTEXT = "task_context"
    SKILL_HISTORY = "skill_history"
    CHAT_CONTEXT = "chat_context"


class Reranker(str, Enum):
    RRF = "rrf"
    NODE_DISTANCE = "node_distance"
    EPISODE_MENTIONS = "episode_mentions"


@dataclass(frozen=True, slots=True)
class RecipeSpec:
    intent: ReadIntent
    reranker: Reranker
    limit: int
    include_closed: bool = False
    relations: tuple[str, ...] = field(default_factory=tuple)
    center_on_skill: bool = False
    summary: str = ""


RECIPES: Mapping[ReadIntent, RecipeSpec] = {
    ReadIntent.STUDENT_NOW: RecipeSpec(
        intent=ReadIntent.STUDENT_NOW,
        reranker=Reranker.RRF,
        limit=6,
        relations=(STRUGGLES_WITH, EXHIBITS, DEMONSTRATES, PREFERS),
        summary="what is true about the student right now",
    ),
    ReadIntent.TASK_CONTEXT: RecipeSpec(
        intent=ReadIntent.TASK_CONTEXT,
        reranker=Reranker.NODE_DISTANCE,
        limit=6,
        relations=(STRUGGLES_WITH, EXHIBITS, DEMONSTRATES),
        center_on_skill=True,
        summary="what usually goes wrong for this student on this kind of task",
    ),
    ReadIntent.SKILL_HISTORY: RecipeSpec(
        intent=ReadIntent.SKILL_HISTORY,
        reranker=Reranker.EPISODE_MENTIONS,
        limit=10,
        include_closed=True,
        relations=(STRUGGLES_WITH, DEMONSTRATES, EXHIBITS),
        center_on_skill=True,
        summary="how this skill changed over time, closed windows included",
    ),
    ReadIntent.CHAT_CONTEXT: RecipeSpec(
        intent=ReadIntent.CHAT_CONTEXT,
        reranker=Reranker.RRF,
        limit=5,
        relations=(STRUGGLES_WITH, EXHIBITS, PREFERS, WORKED_ON),
        summary="personal context for the student's message",
    ),
}


def recipe_for(intent: ReadIntent) -> RecipeSpec:
    return RECIPES[intent]


def default_intent(has_task: bool) -> ReadIntent:
    return ReadIntent.TASK_CONTEXT if has_task else ReadIntent.STUDENT_NOW


def intent_question() -> Question:
    return Choice(
        name="memory_intent",
        instructions=(
            "A student wrote a message to the team. Which slice of their long-term "
            "memory should be loaded before answering?"
        ),
        options={
            ReadIntent.CHAT_CONTEXT.value: (
                "General personal context: what this student is like, what they keep "
                "struggling with, how they prefer to be helped."
            ),
            ReadIntent.TASK_CONTEXT.value: (
                "The message is about the task at hand. Load what usually goes wrong "
                "for this student on this kind of work."
            ),
            ReadIntent.SKILL_HISTORY.value: (
                "The message asks about progress or about one topic over time: "
                "'am I getting better', 'do I still do this'. Load the history of the skill."
            ),
        },
    )


def intent_state(message: str, task_title: str, focus_skill: str) -> dict[str, str]:
    return {
        "message": _clip(message, 1200),
        "task": _clip(task_title, 200),
        "focus_skill": focus_skill or "",
    }


def read_intent(
        answers: Answers,
        min_confidence: float,
        fallback: ReadIntent = ReadIntent.CHAT_CONTEXT,
) -> ReadIntent:
    choice = answers.choice("memory_intent", min_confidence=min_confidence)
    if choice is None:
        return fallback
    try:
        return ReadIntent(choice.value)
    except ValueError:
        return fallback


def intents_in_use() -> Sequence[ReadIntent]:
    return tuple(RECIPES)


def _clip(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"
