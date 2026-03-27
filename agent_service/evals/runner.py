from __future__ import annotations

import asyncio
import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_service.evals.evaluator import evaluate_chat_from_dataset, evaluate_review_from_dataset


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    dataset_path: str
    base_url: str
    timeout_sec: int
    pretty: bool
    output_path: str | None
    max_error_examples: int


def _load_dataset(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _default_report_path() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return os.path.join(reports_dir, f"report_{ts}.json")


def _print_review_summary(report: dict[str, Any], *, max_error_examples: int) -> None:
    review = report.get("review_eval") or {}
    cases: list[dict[str, Any]] = list(review.get("cases") or [])
    aggregated: dict[str, Any] = dict(review.get("aggregated") or {})

    if not cases:
        print("Review eval: no cases.")
        return

    scores: list[int] = []
    for c in cases:
        actual_review = c.get("actual_review") or {}
        score = actual_review.get("score")
        if isinstance(score, int):
            scores.append(score)

    avg_score = (sum(scores) / len(scores)) if scores else None

    accuracy = aggregated.get("score_within_range_rate")
    keyword_mean = aggregated.get("keyword_match_score_mean")
    resp_len_mean = aggregated.get("response_length_chars_mean")

    print("\nReview eval summary")
    print(f"- cases: {len(cases)}")
    if avg_score is not None:
        print(f"- average score: {avg_score:.2f}")
    if isinstance(accuracy, (int, float)):
        print(f"- accuracy (score within range): {float(accuracy) * 100:.1f}%")
    if isinstance(keyword_mean, (int, float)):
        print(f"- keyword_match_score_mean: {float(keyword_mean):.3f}")
    if isinstance(resp_len_mean, (int, float)):
        print(f"- response_length_chars_mean: {float(resp_len_mean):.0f}")

    errors = [
        c
        for c in cases
        if not (c.get("metrics") or {}).get("score_within_range", False)
    ]
    if not errors:
        print("- error examples: none (all cases within range)")
        return

    print("- error examples (showing up to %d):" % max_error_examples)
    for c in errors[:max_error_examples]:
        cid = c.get("id")
        expected = c.get("expected") or {}
        expected_range = expected.get("expected_score_range")
        actual = (c.get("actual_review") or {}).get("score")
        m = c.get("metrics") or {}
        km = m.get("keyword_match_score")
        fb = (c.get("actual_review") or {}).get("feedback") or ""
        fb_short = fb.replace("\n", " ").strip()[:140]

        print(f"  - case {cid}: expected {expected_range}, actual score {actual}, keyword_match={km:.3f}")
        if fb_short:
            print(f"    feedback: {fb_short}...")


def _print_chat_summary(report: dict[str, Any], *, max_error_examples: int) -> None:
    chat = report.get("chat_eval") or {}
    cases: list[dict[str, Any]] = list(chat.get("cases") or [])
    aggregated: dict[str, Any] = dict(chat.get("aggregated") or {})

    if not cases:
        print("Chat eval: no cases.")
        return

    relevance_mean = aggregated.get("keyword_match_score_mean")
    accuracy = aggregated.get("key_ideas_present_rate")
    resp_len_mean = aggregated.get("response_length_chars_mean")

    print("\nChat eval summary")
    print(f"- cases: {len(cases)}")
    if isinstance(relevance_mean, (int, float)):
        print(f"- avg keyword_match_score (relevance): {float(relevance_mean):.3f}")
    if isinstance(accuracy, (int, float)):
        print(f"- accuracy (has key ideas): {float(accuracy) * 100:.1f}%")
    if isinstance(resp_len_mean, (int, float)):
        print(f"- response_length_chars_mean: {float(resp_len_mean):.0f}")

    errors = [
        c
        for c in cases
        if not (c.get("metrics") or {}).get("key_ideas_present", False)
    ]
    if not errors:
        print("- error examples: none (all cases contain key ideas)")
        return

    print("- error examples (showing up to %d):" % max_error_examples)
    for c in errors[:max_error_examples]:
        cid = c.get("id")
        expected = c.get("expected") or {}
        expected_keywords = expected.get("expected_keywords") or []
        actual = c.get("actual_answer") or ""
        m = c.get("metrics") or {}
        km = m.get("keyword_match_score")
        print(f"  - case {cid}: expected_keywords={expected_keywords}, keyword_match={km:.3f}")
        snippet = str(actual).replace("\n", " ").strip()[:160]
        if snippet:
            print(f"    answer: {snippet}...")


def run(config: RunnerConfig) -> dict[str, Any]:
    logger = logging.getLogger("evals.runner")
    _ = (config.base_url, config.timeout_sec)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": config.dataset_path,
        "base_url": config.base_url,
        "chat": None,
        "review_eval": None,
    }

    async def _run_all() -> dict[str, Any]:
        logger.info("Running chat eval (in-process use case calls)")
        chat_eval = await evaluate_chat_from_dataset(dataset_path=config.dataset_path, logger=logger)

        logger.info("Running review eval (in-process use case calls)")
        review_eval = await evaluate_review_from_dataset(dataset_path=config.dataset_path, logger=logger)

        return {"chat_eval": chat_eval, "review_eval": review_eval}

    results = asyncio.run(_run_all())
    report["chat_eval"] = results["chat_eval"]
    report["review_eval"] = results["review_eval"]

    output_path = config.output_path or _default_report_path()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2 if config.pretty else None)
    logger.info("Saved report: %s", output_path)

    _print_chat_summary(report, max_error_examples=config.max_error_examples)
    _print_review_summary(report, max_error_examples=config.max_error_examples)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run external evaluation scenarios for programming-edu-service.")
    parser.add_argument(
        "--dataset",
        default=os.path.join(os.path.dirname(__file__), "dataset", "submissions.json"),
        help="Path to dataset JSON (default: evals/dataset/submissions.json).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AGENT_SERVICE_BASE_URL", "http://localhost:8000/api"),
        help="Base URL to agent_service, including /api (default: env AGENT_SERVICE_BASE_URL or http://localhost:8000/api).",
    )
    parser.add_argument("--timeout-sec", type=int, default=60, help="HTTP timeout in seconds.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print saved output JSON.")
    parser.add_argument("--output", default=None, help="Optional path to write report JSON.")
    parser.add_argument(
        "--max-error-examples",
        type=int,
        default=5,
        help="Max number of cases to show when score is outside expected range.",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase logging verbosity.")

    args = parser.parse_args()
    _setup_logging(args.verbose)

    config = RunnerConfig(
        dataset_path=args.dataset,
        base_url=args.base_url,
        timeout_sec=args.timeout_sec,
        pretty=args.pretty,
        output_path=args.output,
        max_error_examples=args.max_error_examples,
    )
    report = run(config)
    if config.pretty:
        print("\nFull report JSON:")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
