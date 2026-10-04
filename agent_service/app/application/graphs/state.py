from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


class ReviewState(TypedDict):
    code: str
    task_description: str
    task_id: NotRequired[str | None]
    submission_id: NotRequired[str | None]
    user_id: NotRequired[str | None]
    attempt: NotRequired[int | None]
    previous_feedback: NotRequired[str | None]
    hidden_tests: NotRequired[str | None]
    trace_id: NotRequired[str]
    tool_facts: NotRequired[str]
    tool_report: NotRequired[Any]
    rubric: NotRequired[Any]
    reviewer_review: NotRequired[Any]
    bug_review: NotRequired[Any]
    checks: NotRequired[list[Any]]
    challenge: NotRequired[Any]
    path: NotRequired[Any]
    mentor_feedback: NotRequired[str]
    mentor_ok: NotRequired[bool]
    draft_card: NotRequired[Any]
    n_drafts: NotRequired[int]
    path_verdict: NotRequired[Any]
    review: NotRequired[Any]


class ChatState(TypedDict):
    message: str
    chat_history: list[Any]
    user_context: NotRequired[Any]
    trajectory_action: NotRequired[str | None]
    mode: NotRequired[str]
    speaker_id: NotRequired[str]
    speaker_name: NotRequired[str]
    speaker_role: NotRequired[str]
    route_reason: NotRequired[str]
    route_source: NotRequired[str]
    advisors: NotRequired[list[str]]
    briefing: NotRequired[str]
    answer: NotRequired[str]
    path: NotRequired[Any]
    result: NotRequired[Any]


@dataclass
class ReviewGraphRuntime:
    orchestrator: Any
    logger: Any
    trace_id: str
    tracer: Any = None


@dataclass
class ChatGraphRuntime:
    orchestrator: Any
    tracer: Any = None
