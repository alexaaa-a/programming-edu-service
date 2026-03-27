from typing import Protocol

from agent_service.app.application.dto import Review
from agent_service.app.application.eval import ReviewEvaluationMetrics


class ReviewMetricsCalculator(Protocol):
    def compute(self, *, expected: Review, actual: Review) -> ReviewEvaluationMetrics:
        raise NotImplementedError
