from __future__ import annotations

import logging
import json
from dataclasses import asdict, dataclass
from typing import Any


from agent_service.evals.metrics import (
    count_keywords_found,
    keyword_match_score,
    response_length,
    score_within_range,
)


@dataclass(frozen=True, slots=True)
class ReviewEvalCase:
    id: str
    submission_id: str
    task_description: str
    code: str
    expected_keywords: list[str]
    expected_score_range: list[int]


@dataclass(frozen=True, slots=True)
class ReviewCaseMetrics:
    keyword_match_score: float
    score_within_range: bool
    response_length_chars: int


@dataclass(frozen=True, slots=True)
class ChatEvalCase:
    id: str
    session_id: str
    user_message: str
    expected_keywords: list[str]


@dataclass(frozen=True, slots=True)
class ChatCaseMetrics:
    keyword_match_score: float
    expected_keywords_total: int
    expected_keywords_found: int
    key_ideas_present: bool
    response_length_chars: int
    answer_non_empty: bool


def load_dataset(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_review_cases(raw: dict[str, Any]) -> list[ReviewEvalCase]:
    tests = raw.get("review_tests", [])
    if not isinstance(tests, list):
        return []

    cases: list[ReviewEvalCase] = []
    for i, t in enumerate(tests):
        if not isinstance(t, dict):
            continue
        task_description = str(t.get("task_description", ""))
        code = str(t.get("code", ""))
        expected_keywords = [str(x) for x in t.get("expected_keywords", []) if isinstance(x, str)]
        expected_score_range_raw = t.get("expected_score_range", [5, 7])
        if not isinstance(expected_score_range_raw, list) or len(expected_score_range_raw) != 2:
            expected_score_range = [5, 7]
        else:
            expected_score_range = [int(expected_score_range_raw[0]), int(expected_score_range_raw[1])]

        submission_id = str(t.get("submission_id", t.get("id", f"sub_{i+1:03d}")))
        case_id = str(t.get("id", f"case_{i+1:03d}"))

        cases.append(
            ReviewEvalCase(
                id=case_id,
                submission_id=submission_id,
                task_description=task_description,
                code=code,
                expected_keywords=expected_keywords,
                expected_score_range=expected_score_range,
            )
        )
    return cases


def parse_chat_cases(raw: dict[str, Any]) -> list[ChatEvalCase]:
    tests = raw.get("chat_tests", [])
    if not isinstance(tests, list):
        return []

    cases: list[ChatEvalCase] = []
    for i, t in enumerate(tests):
        if not isinstance(t, dict):
            continue

        user_message = str(t.get("user_message", ""))
        expected_keywords = [str(x) for x in t.get("expected_keywords", []) if isinstance(x, str)]

        case_id = str(t.get("id", f"chat_case_{i+1:03d}"))
        session_id = str(t.get("session_id", f"chat_eval_session_{case_id}"))

        cases.append(
            ChatEvalCase(
                id=case_id,
                session_id=session_id,
                user_message=user_message,
                expected_keywords=expected_keywords,
            )
        )

    return cases


class ReviewEvaluator:
    def __init__(self, *, review_submission_use_case: Any, logger: logging.Logger | None = None) -> None:
        self._review_submission_use_case = review_submission_use_case
        self._logger = logger or logging.getLogger(__name__)

    async def evaluate(self, *, cases: list[ReviewEvalCase]) -> dict[str, Any]:
        per_case: list[dict[str, Any]] = []
        keyword_scores: list[float] = []
        within_range_flags: list[bool] = []
        response_lengths: list[int] = []

        for c in cases:
            self._logger.info("Evaluating case=%s submission=%s", c.id, c.submission_id)

            submission_result = await self._review_submission_use_case(
                submission_id=c.submission_id,
                code=c.code,
                task_description=c.task_description,
            )
            actual_review = submission_result.review

            actual_text = actual_review.feedback + "\n" + "\n".join(actual_review.suggestions)

            metrics = ReviewCaseMetrics(
                keyword_match_score=keyword_match_score(
                    answer=actual_text,
                    expected_keywords=c.expected_keywords,
                ),
                score_within_range=score_within_range(
                    score=actual_review.score,
                    expected_score_range=c.expected_score_range,
                ),
                response_length_chars=response_length(actual_review.feedback, unit="chars"),
            )

            keyword_scores.append(metrics.keyword_match_score)
            within_range_flags.append(metrics.score_within_range)
            response_lengths.append(metrics.response_length_chars)

            per_case.append(
                {
                    "id": c.id,
                    "submission_id": c.submission_id,
                    "task_description": c.task_description,
                    "expected": {
                        "expected_keywords": c.expected_keywords,
                        "expected_score_range": c.expected_score_range,
                    },
                    "actual_review": asdict(actual_review),
                    "metrics": asdict(metrics),
                }
            )

        total = len(cases)
        aggregated = {
            "total_cases": total,
            "keyword_match_score_mean": (sum(keyword_scores) / total) if total else 0.0,
            "score_within_range_rate": (sum(int(x) for x in within_range_flags) / total) if total else 0.0,
            "response_length_chars_mean": (sum(response_lengths) / total) if total else 0.0,
        }

        return {
            "type": "review_eval",
            "aggregated": aggregated,
            "cases": per_case,
        }


async def evaluate_review_from_dataset(
    *,
    dataset_path: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    from agent_service.app.application.use_cases import ReviewSubmissionUseCase
    from agent_service.app.config import Settings
    from agent_service.app.setup.ioc import create_container

    log = logger or logging.getLogger(__name__)
    raw = load_dataset(dataset_path)
    cases = parse_review_cases(raw)
    if not cases:
        return {"type": "review_eval", "aggregated": {"total_cases": 0}, "cases": []}

    container = create_container(Settings())
    try:
        review_submission_use_case = await container.get(ReviewSubmissionUseCase)
        evaluator = ReviewEvaluator(
            review_submission_use_case=review_submission_use_case,
            logger=log,
        )
        return await evaluator.evaluate(cases=cases)
    finally:
        await container.close()


class ChatEvaluator:
    def __init__(self, *, chat_with_team_use_case: Any, logger: logging.Logger | None = None) -> None:
        self._chat_with_team_use_case = chat_with_team_use_case
        self._logger = logger or logging.getLogger(__name__)

    async def evaluate(self, *, cases: list[ChatEvalCase]) -> dict[str, Any]:
        per_case: list[dict[str, Any]] = []
        scores: list[float] = []
        key_ideas_flags: list[bool] = []
        response_lengths: list[int] = []

        for c in cases:
            self._logger.info("Chat evaluating case=%s session=%s", c.id, c.session_id)
            chat_result = await self._chat_with_team_use_case(message=c.user_message, session_id=c.session_id)
            answer = chat_result.answer

            found, total = count_keywords_found(answer, c.expected_keywords, case_sensitive=False)
            score = (found / total) if total else 0.0
            key_ideas_present = bool(total) and found > 0

            metrics = ChatCaseMetrics(
                keyword_match_score=score,
                expected_keywords_total=total,
                expected_keywords_found=found,
                key_ideas_present=key_ideas_present,
                response_length_chars=response_length(answer, unit="chars"),
                answer_non_empty=bool(answer and answer.strip()),
            )

            per_case.append(
                {
                    "id": c.id,
                    "session_id": c.session_id,
                    "user_message": c.user_message,
                    "expected": {"expected_keywords": c.expected_keywords},
                    "actual_answer": answer,
                    "metrics": asdict(metrics),
                }
            )

            scores.append(metrics.keyword_match_score)
            key_ideas_flags.append(metrics.key_ideas_present)
            response_lengths.append(metrics.response_length_chars)

        total_cases = len(cases)
        aggregated = {
            "total_cases": total_cases,
            "keyword_match_score_mean": (sum(scores) / total_cases) if total_cases else 0.0,
            "key_ideas_present_rate": (sum(int(x) for x in key_ideas_flags) / total_cases) if total_cases else 0.0,
            "response_length_chars_mean": (sum(response_lengths) / total_cases) if total_cases else 0.0,
        }

        return {"type": "chat_eval", "aggregated": aggregated, "cases": per_case}


async def evaluate_chat_from_dataset(
    *,
    dataset_path: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    from agent_service.app.application.use_cases import ChatWithTeamUseCase
    from agent_service.app.config import Settings
    from agent_service.app.setup.ioc import create_container

    log = logger or logging.getLogger(__name__)
    raw = load_dataset(dataset_path)
    cases = parse_chat_cases(raw)
    if not cases:
        return {"type": "chat_eval", "aggregated": {"total_cases": 0}, "cases": []}

    container = create_container(Settings())
    try:
        chat_use_case = await container.get(ChatWithTeamUseCase)
        evaluator = ChatEvaluator(chat_with_team_use_case=chat_use_case, logger=log)
        return await evaluator.evaluate(cases=cases)
    finally:
        await container.close()
