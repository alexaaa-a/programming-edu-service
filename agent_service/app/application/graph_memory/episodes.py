from hashlib import sha256
from typing import Any

from agent_service.app.application.dto import Review
from agent_service.app.application.graph_memory.facts import (
    EpisodeKind,
    MemoryEpisode,
    utc_now,
)


MAX_CRITERIA = 12
MAX_CHALLENGES = 4
MAX_BODY_CHARS = 3000


def review_episode(
        user_id: str,
        review: Review,
        report: Any | None = None,
        task_id: str | None = None,
        submission_id: str | None = None,
        task_title: str = "",
        mastery: dict[str, float] | None = None,
) -> MemoryEpisode:
    observations: list[dict[str, Any]] = [{"kind": "score", "value": int(review.score)}]

    for item in (review.criteria or [])[:MAX_CRITERIA]:
        observations.append(
            {
                "kind": "criterion",
                "passed": bool(item.passed),
                "text": str(item.text or ""),
                "note": str(item.note or ""),
            }
        )

    for item in (review.challenges or [])[:MAX_CHALLENGES]:
        observations.append(
            {
                "kind": "challenge",
                "text": str(item.text or ""),
                "severity": str(item.severity or "medium"),
            }
        )

    tests = _tests_observation(review, report)
    if tests is not None:
        observations.append(tests)

    return MemoryEpisode(
        episode_id=_episode_id("review", submission_id or "", user_id, review.feedback),
        kind=EpisodeKind.REVIEW,
        user_id=str(user_id),
        occurred_at=utc_now(),
        body=_review_body(review),
        task_id=str(task_id) if task_id else None,
        submission_id=str(submission_id) if submission_id else None,
        task_title=task_title,
        observations=observations,
        mastery=dict(mastery or {}),
    )


def chat_episode(
        user_id: str,
        session_id: str,
        message: str,
        speaker: str,
        answer: str,
        task_id: str | None = None,
        task_title: str = "",
        turn_id: str = "",
        mastery: dict[str, float] | None = None,
) -> MemoryEpisode:
    body = f"Student: {message.strip()}\n{speaker.strip()}: {answer.strip()}"
    return MemoryEpisode(
        episode_id=_episode_id("chat", f"{session_id}:{turn_id}", user_id, message),
        kind=EpisodeKind.CHAT,
        user_id=str(user_id),
        occurred_at=utc_now(),
        body=body[:MAX_BODY_CHARS],
        task_id=str(task_id) if task_id else None,
        session_id=str(session_id) if session_id else None,
        task_title=task_title,
        observations=[],
        mastery=dict(mastery or {}),
    )


def _tests_observation(review: Review, report: Any | None) -> dict[str, Any] | None:
    tests = getattr(review, "tests", None)
    if tests is not None:
        return {
            "kind": "hidden_tests",
            "status": str(getattr(tests, "status", "") or ""),
            "total": int(getattr(tests, "total", 0) or 0),
            "passed": int(getattr(tests, "passed", 0) or 0),
            "failed_names": [str(name) for name in (getattr(tests, "failed_names", None) or [])][:8],
        }
    hidden = getattr(report, "hidden", None) if report is not None else None
    if hidden is None:
        return None
    return {
        "kind": "hidden_tests",
        "status": str(getattr(hidden, "status", "") or ""),
        "total": int(getattr(hidden, "total", 0) or 0),
        "passed": int(getattr(hidden, "passed", 0) or 0),
        "failed_names": [str(name) for name in (getattr(hidden, "failed_names", None) or [])][:8],
    }


def _review_body(review: Review) -> str:
    bits: list[str] = [f"Score: {review.score}/10", (review.feedback or "").strip()]
    if review.suggestions:
        bits.append("Suggestions: " + "; ".join(str(item) for item in review.suggestions[:5]))
    return "\n".join(part for part in bits if part)[:MAX_BODY_CHARS]


def _episode_id(prefix: str, key: str, user_id: str, payload: str) -> str:
    digest = sha256(f"{user_id}|{key}|{payload}".encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"
