import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_service.evals.evaluator import evaluate_chat_from_dataset, evaluate_review_from_dataset
from agent_service.evals.offline import evaluate_offline_cases


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    dataset_path: str
    suite: str
    pretty: bool
    output_path: str | None
    max_error_examples: int


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _default_report_path() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return os.path.join(reports_dir, f"report_{stamp}.json")


def _print_offline(report: dict[str, Any]) -> None:
    block = report.get("offline_eval") or {}
    agg = dict(block.get("aggregated") or {})
    cases = list(block.get("cases") or [])
    print("\nOffline eval (tools + rubric, no LLM)")
    print(f"- cases: {agg.get('total_cases', 0)}")
    print(f"- pass_rate: {float(agg.get('pass_rate') or 0) * 100:.1f}%")
    failed = [c for c in cases if not c.get("passed")]
    if not failed:
        print("- failures: none")
        return
    print("- failures:")
    for case in failed:
        print(f"  - {case.get('id')}: {case.get('failures')}")


def _print_review(report: dict[str, Any], max_error_examples: int) -> None:
    block = report.get("review_eval") or {}
    if block.get("error"):
        print(f"\nReview eval skipped: {block['error']}")
        return
    cases = list(block.get("cases") or [])
    agg = dict(block.get("aggregated") or {})
    if not cases:
        print("\nReview eval: no cases.")
        return
    print("\nReview eval (LLM pipeline)")
    print(f"- cases: {len(cases)}")
    print(f"- pass_rate: {float(agg.get('pass_rate') or 0) * 100:.1f}%")
    print(f"- score in range: {float(agg.get('score_within_range_rate') or 0) * 100:.1f}%")
    print(f"- mention groups: {float(agg.get('mention_groups_score_mean') or 0):.3f}")
    errors = [c for c in cases if not (c.get("metrics") or {}).get("passed")]
    if not errors:
        print("- failures: none")
        return
    print(f"- failures (up to {max_error_examples}):")
    for case in errors[:max_error_examples]:
        expected = case.get("expected") or {}
        actual = (case.get("actual_review") or {}).get("score")
        print(
            f"  - {case.get('id')}: score {actual}, expected {expected.get('expected_score_range')}"
        )


def _print_chat(report: dict[str, Any], max_error_examples: int) -> None:
    block = report.get("chat_eval") or {}
    if block.get("error"):
        print(f"\nChat eval skipped: {block['error']}")
        return
    cases = list(block.get("cases") or [])
    agg = dict(block.get("aggregated") or {})
    if not cases:
        print("\nChat eval: no cases.")
        return
    print("\nChat eval (team router + personas)")
    print(f"- cases: {len(cases)}")
    print(f"- pass_rate: {float(agg.get('pass_rate') or 0) * 100:.1f}%")
    print(f"- speaker match: {float(agg.get('speaker_match_rate') or 0) * 100:.1f}%")
    print(f"- mention groups: {float(agg.get('mention_groups_score_mean') or 0):.3f}")
    errors = [c for c in cases if not (c.get("metrics") or {}).get("passed")]
    if not errors:
        print("- failures: none")
        return
    print(f"- failures (up to {max_error_examples}):")
    for case in errors[:max_error_examples]:
        print(
            f"  - {case.get('id')}: speaker {case.get('actual_speaker')} "
            f"mode {case.get('actual_mode')}"
        )


def run(config: RunnerConfig) -> dict[str, Any]:
    logger = logging.getLogger("evals.runner")
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": config.dataset_path,
        "suite": config.suite,
        "offline_eval": None,
        "review_eval": None,
        "chat_eval": None,
    }

    if config.suite in {"offline", "all"}:
        report["offline_eval"] = evaluate_offline_cases()

    if config.suite in {"llm", "all"}:

        async def _llm() -> dict[str, Any]:
            out: dict[str, Any] = {}
            try:
                out["review_eval"] = await evaluate_review_from_dataset(
                    dataset_path=config.dataset_path,
                    logger=logger,
                )
            except Exception as exc:
                logger.exception("review eval failed")
                out["review_eval"] = {"type": "review_eval", "error": str(exc), "cases": []}
            try:
                out["chat_eval"] = await evaluate_chat_from_dataset(
                    dataset_path=config.dataset_path,
                    logger=logger,
                )
            except Exception as exc:
                logger.exception("chat eval failed")
                out["chat_eval"] = {"type": "chat_eval", "error": str(exc), "cases": []}
            return out

        llm = asyncio.run(_llm())
        report["review_eval"] = llm.get("review_eval")
        report["chat_eval"] = llm.get("chat_eval")

    output_path = config.output_path or _default_report_path()
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2 if config.pretty else None)
    logger.info("Saved report: %s", output_path)

    if report.get("offline_eval"):
        _print_offline(report)
    if config.suite in {"llm", "all"}:
        _print_review(report, max_error_examples=config.max_error_examples)
        _print_chat(report, max_error_examples=config.max_error_examples)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval suites for programming-edu-service agents.")
    parser.add_argument(
        "--dataset",
        default=os.path.join(os.path.dirname(__file__), "dataset", "submissions.json"),
    )
    parser.add_argument(
        "--suite",
        choices=("offline", "llm", "all"),
        default="offline",
        help="offline = tools+rubric without LLM (default). llm = live pipeline. all = both.",
    )
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-error-examples", type=int, default=5)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()
    _setup_logging(args.verbose)
    run(
        RunnerConfig(
            dataset_path=args.dataset,
            suite=args.suite,
            pretty=args.pretty,
            output_path=args.output,
            max_error_examples=args.max_error_examples,
        )
    )


if __name__ == "__main__":
    main()
