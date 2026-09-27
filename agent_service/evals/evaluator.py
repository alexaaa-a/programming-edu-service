import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from agent_service.evals.metrics import mention_groups_score, response_length, score_within_range
from agent_service.app.application.use_cases import ReviewSubmissionUseCase
from agent_service.app.config import Settings
from agent_service.app.setup.ioc import create_container
from agent_service.app.application.use_cases import ChatWithTeamUseCase


@dataclass(frozen=True, slots=True)
class ReviewEvalCase:
    id: str
    submission_id: str
    task_description: str
    code: str
    must_mention_any: list[list[str]] = field(default_factory=list)
    expected_score_range: list[int] = field(default_factory=lambda: [1, 10])


@dataclass(frozen=True, slots=True)
class ChatEvalCase:
    id: str
    session_id: str
    user_message: str
    must_mention_any: list[list[str]] = field(default_factory=list)
    expected_speaker: str | None = None
    expected_mode: str | None = None


def load_dataset(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _mention_groups(raw: Any) -> list[list[str]]:
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return [[str(item) for item in group if str(item).strip()] for group in raw]
    if isinstance(raw, list):
        return [[str(item)] for item in raw if str(item).strip()]
    return []


def parse_review_cases(raw: dict[str, Any]) -> list[ReviewEvalCase]:
    tests = raw.get("review_tests", [])
    if not isinstance(tests, list):
        return []
    cases: list[ReviewEvalCase] = []
    for i, item in enumerate(tests):
        if not isinstance(item, dict):
            continue
        range_raw = item.get("expected_score_range", [1, 10])
        if not isinstance(range_raw, list) or len(range_raw) != 2:
            score_range = [1, 10]
        else:
            score_range = [int(range_raw[0]), int(range_raw[1])]
        mentions = _mention_groups(item.get("must_mention_any") or item.get("expected_keywords") or [])
        cases.append(
            ReviewEvalCase(
                id=str(item.get("id", f"case_{i + 1:03d}")),
                submission_id=str(item.get("submission_id", item.get("id", f"sub_{i + 1:03d}"))),
                task_description=str(item.get("task_description", "")),
                code=str(item.get("code", "")),
                must_mention_any=mentions,
                expected_score_range=score_range,
            )
        )
    return cases


def parse_chat_cases(raw: dict[str, Any]) -> list[ChatEvalCase]:
    tests = raw.get("chat_tests", [])
    if not isinstance(tests, list):
        return []
    cases: list[ChatEvalCase] = []
    for i, item in enumerate(tests):
        if not isinstance(item, dict):
            continue
        mentions = _mention_groups(item.get("must_mention_any") or item.get("expected_keywords") or [])
        speaker = item.get("expected_speaker")
        mode = item.get("expected_mode")
        cases.append(
            ChatEvalCase(
                id=str(item.get("id", f"chat_case_{i + 1:03d}")),
                session_id=str(item.get("session_id", f"chat_eval_{i + 1:03d}")),
                user_message=str(item.get("user_message", "")),
                must_mention_any=mentions,
                expected_speaker=str(speaker) if speaker else None,
                expected_mode=str(mode) if mode else None,
            )
        )
    return cases


class ReviewEvaluator:
    def __init__(self, review_submission_use_case: Any, logger: logging.Logger | None = None) -> None:
        self._review_submission_use_case = review_submission_use_case
        self._logger = logger or logging.getLogger(__name__)

    async def evaluate(self, *, cases: list[ReviewEvalCase]) -> dict[str, Any]:
        per_case: list[dict[str, Any]] = []
        mention_scores: list[float] = []
        within: list[bool] = []
        passed_flags: list[bool] = []

        for case in cases:
            self._logger.info("Evaluating case=%s submission=%s", case.id, case.submission_id)
            result = await self._review_submission_use_case(
                submission_id=case.submission_id,
                code=case.code,
                task_description=case.task_description,
            )
            review = result.review
            text = review.feedback + "\n" + "\n".join(review.suggestions)
            mention, hits, total = mention_groups_score(text, case.must_mention_any)
            in_range = score_within_range(review.score, case.expected_score_range)
            path_names = [step.name for step in review.agent_path]
            required = {"tools", "reviewer", "bug", "mentor"}
            path_ok = required.issubset(set(path_names))
            passed = in_range and mention >= 0.5 and path_ok
            mention_scores.append(mention)
            within.append(in_range)
            passed_flags.append(passed)
            per_case.append(
                {
                    "id": case.id,
                    "submission_id": case.submission_id,
                    "expected": {
                        "must_mention_any": case.must_mention_any,
                        "expected_score_range": case.expected_score_range,
                    },
                    "actual_review": asdict(review),
                    "metrics": {
                        "mention_groups_score": mention,
                        "mention_groups_hits": hits,
                        "mention_groups_total": total,
                        "score_within_range": in_range,
                        "path_ok": path_ok,
                        "path_steps": path_names,
                        "passed": passed,
                        "response_length_chars": response_length(review.feedback),
                    },
                }
            )

        total_cases = len(cases)
        return {
            "type": "review_eval",
            "aggregated": {
                "total_cases": total_cases,
                "mention_groups_score_mean": (sum(mention_scores) / total_cases) if total_cases else 0.0,
                "score_within_range_rate": (sum(within) / total_cases) if total_cases else 0.0,
                "pass_rate": (sum(passed_flags) / total_cases) if total_cases else 0.0,
            },
            "cases": per_case,
        }


async def evaluate_review_from_dataset(
        dataset_path: str,
        logger: logging.Logger | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    cases = parse_review_cases(load_dataset(dataset_path))
    if not cases:
        return {"type": "review_eval", "aggregated": {"total_cases": 0}, "cases": []}

    container = create_container(Settings())
    try:
        use_case = await container.get(ReviewSubmissionUseCase)
        return await ReviewEvaluator(review_submission_use_case=use_case, logger=log).evaluate(cases=cases)
    finally:
        await container.close()


class ChatEvaluator:
    def __init__(self, chat_with_team_use_case: Any, logger: logging.Logger | None = None) -> None:
        self._chat_with_team_use_case = chat_with_team_use_case
        self._logger = logger or logging.getLogger(__name__)

    async def evaluate(self, cases: list[ChatEvalCase]) -> dict[str, Any]:
        per_case: list[dict[str, Any]] = []
        mention_scores: list[float] = []
        speaker_hits: list[bool] = []
        passed_flags: list[bool] = []

        for case in cases:
            self._logger.info("Chat evaluating case=%s session=%s", case.id, case.session_id)
            result = await self._chat_with_team_use_case(message=case.user_message, session_id=case.session_id)
            mention, hits, total = mention_groups_score(result.answer, case.must_mention_any)
            speaker_ok = case.expected_speaker is None or str(result.speaker_id) == case.expected_speaker
            mode_ok = case.expected_mode is None or str(result.mode) == case.expected_mode
            path_names = [step.name for step in result.agent_path]
            path_ok = "route" in path_names and "speaker" in path_names
            if result.mode == "huddle":
                path_ok = path_ok and "advisor" in path_names and bool(result.advisors)
            passed = bool(result.answer.strip()) and mention >= 0.5 and speaker_ok and mode_ok and path_ok
            mention_scores.append(mention)
            speaker_hits.append(speaker_ok)
            passed_flags.append(passed)
            per_case.append(
                {
                    "id": case.id,
                    "session_id": case.session_id,
                    "user_message": case.user_message,
                    "expected": {
                        "must_mention_any": case.must_mention_any,
                        "expected_speaker": case.expected_speaker,
                        "expected_mode": case.expected_mode,
                    },
                    "actual_answer": result.answer,
                    "actual_speaker": result.speaker_id,
                    "actual_mode": result.mode,
                    "actual_advisors": list(result.advisors),
                    "actual_path": path_names,
                    "metrics": {
                        "mention_groups_score": mention,
                        "mention_groups_hits": hits,
                        "mention_groups_total": total,
                        "speaker_match": speaker_ok,
                        "mode_match": mode_ok,
                        "path_ok": path_ok,
                        "passed": passed,
                        "response_length_chars": response_length(result.answer),
                    },
                }
            )

        total_cases = len(cases)
        return {
            "type": "chat_eval",
            "aggregated": {
                "total_cases": total_cases,
                "mention_groups_score_mean": (sum(mention_scores) / total_cases) if total_cases else 0.0,
                "speaker_match_rate": (sum(speaker_hits) / total_cases) if total_cases else 0.0,
                "pass_rate": (sum(passed_flags) / total_cases) if total_cases else 0.0,
            },
            "cases": per_case,
        }


async def evaluate_chat_from_dataset(
        dataset_path: str,
        logger: logging.Logger | None = None,
) -> dict[str, Any]:
    log = logger or logging.getLogger(__name__)
    cases = parse_chat_cases(load_dataset(dataset_path))
    if not cases:
        return {"type": "chat_eval", "aggregated": {"total_cases": 0}, "cases": []}

    container = create_container(Settings())
    try:
        use_case = await container.get(ChatWithTeamUseCase)
        return await ChatEvaluator(chat_with_team_use_case=use_case, logger=log).evaluate(cases=cases)
    finally:
        await container.close()
