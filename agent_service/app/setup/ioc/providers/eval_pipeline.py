import logging

from dishka import Provider, Scope, provide

from agent_service.app.application.eval.interfaces.eval_repository import EvalRunRepository
from agent_service.app.application.eval.interfaces.review_metrics_calculator import (
    ReviewMetricsCalculator,
)
from agent_service.app.application.use_cases.compare_review_evaluation_runs import (
    CompareReviewEvaluationRunsUseCase,
)
from agent_service.app.application.use_cases.evaluate_review_tests import (
    EvaluateReviewTestsUseCase,
)
from agent_service.app.application.use_cases.review_submission import ReviewSubmissionUseCase
from agent_service.app.application.use_cases.evaluate_rag_search import (
    EvaluateRagSearchUseCase,
    RagEvalTestCase,
)
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.infrastructure.eval import (
    InMemoryEvalRunRepository,
    SimpleReviewMetricsCalculator,
)


class EvalRepositoryProvider(Provider):
    @provide(scope=Scope.APP)
    def eval_run_repository(self) -> EvalRunRepository:
        return InMemoryEvalRunRepository()


class ReviewMetricsCalculatorProvider(Provider):
    @provide(scope=Scope.APP)
    def review_metrics_calculator(self) -> ReviewMetricsCalculator:
        return SimpleReviewMetricsCalculator()


class EvaluateReviewTestsUseCaseProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def evaluate_review_tests_use_case(
            self,
            review_submission_use_case: ReviewSubmissionUseCase,
            eval_run_repository: EvalRunRepository,
            review_metrics_calculator: ReviewMetricsCalculator,
    ) -> EvaluateReviewTestsUseCase:
        return EvaluateReviewTestsUseCase(
            review_submission_use_case=review_submission_use_case,
            eval_run_repository=eval_run_repository,
            metrics_calculator=review_metrics_calculator,
        )


class CompareReviewEvaluationRunsUseCaseProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def compare_review_evaluation_runs_use_case(
            self,
            eval_run_repository: EvalRunRepository,
    ) -> CompareReviewEvaluationRunsUseCase:
        return CompareReviewEvaluationRunsUseCase(eval_run_repository=eval_run_repository)


class EvaluateRagSearchUseCaseProvider(Provider):
    @provide(scope=Scope.APP)
    def evaluate_rag_search_use_case(
            self,
            memory: MemoryInterface,
            metrics_recorder: MetricsRecorder,
            logger: logging.Logger,
    ) -> EvaluateRagSearchUseCase:
        test_cases = [
            RagEvalTestCase(
                query="Как улучшить читаемость кода и следовать best practices в Python?",
                expected_types={"best_practice"},
                k=5,
            ),
            RagEvalTestCase(
                query="Найди потенциальные баги и edge cases. Какие типичные ошибки встречаются в паттернах с bug?",
                expected_types={"bugs"},
                k=5,
            ),
            RagEvalTestCase(
                query="Что такое чистый код и как использовать clean code принципы?",
                expected_types={"best_practice"},
                k=5,
            ),
        ]

        return EvaluateRagSearchUseCase(
            memory=memory,
            metrics=metrics_recorder,
            logger=logger,
            test_cases=test_cases,
        )


EvalPipelineProviders = [
    EvalRepositoryProvider(),
    ReviewMetricsCalculatorProvider(),
    EvaluateReviewTestsUseCaseProvider(),
    CompareReviewEvaluationRunsUseCaseProvider(),
    EvaluateRagSearchUseCaseProvider(),
]

