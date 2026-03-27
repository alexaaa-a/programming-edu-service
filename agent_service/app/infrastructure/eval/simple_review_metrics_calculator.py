from __future__ import annotations

import re

from agent_service.app.application.eval.interfaces.review_metrics_calculator import (
    ReviewMetricsCalculator,
)
from agent_service.app.application.eval import ReviewEvaluationMetrics
from agent_service.app.application.dto import Review


class SimpleReviewMetricsCalculator(ReviewMetricsCalculator):
    def compute(self, *, expected: Review, actual: Review) -> ReviewEvaluationMetrics:
        score_diff = expected.score - actual.score
        score_abs_error = float(abs(score_diff))
        score_squared_error = float(score_diff**2)

        expected_tokens = _tokenize(expected.feedback)
        actual_tokens = _tokenize(actual.feedback)
        feedback_jaccard = _jaccard(expected_tokens, actual_tokens)

        expected_suggestions = {_normalize_suggestion(s) for s in expected.suggestions}
        actual_suggestions = {_normalize_suggestion(s) for s in actual.suggestions}
        suggestions_precision, suggestions_recall, suggestions_f1 = _precision_recall_f1(
            expected=expected_suggestions,
            actual=actual_suggestions,
        )

        return ReviewEvaluationMetrics(
            score_abs_error=score_abs_error,
            score_squared_error=score_squared_error,
            feedback_jaccard=feedback_jaccard,
            suggestions_precision=suggestions_precision,
            suggestions_recall=suggestions_recall,
            suggestions_f1=suggestions_f1,
        )


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _normalize_suggestion(s: str) -> str:
    return s.strip().lower()


def _precision_recall_f1(*, expected: set[str], actual: set[str]) -> tuple[float, float, float]:
    if not expected and not actual:
        return 1.0, 1.0, 1.0
    if not actual and expected:
        return 0.0, 0.0, 0.0
    if not expected and actual:
        return 0.0, 0.0, 0.0

    tp = len(expected & actual)
    precision = tp / len(actual) if actual else 0.0
    recall = tp / len(expected) if expected else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return float(precision), float(recall), float(f1)
