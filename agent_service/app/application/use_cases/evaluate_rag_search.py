import logging
from dataclasses import dataclass
from typing import Sequence

from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.infrastructure.observability.timer import Timer


@dataclass(frozen=True, slots=True)
class RagEvalTestCase:
    query: str
    expected_types: set[str]
    k: int = 5


@dataclass(frozen=True, slots=True)
class RagEvalCaseResult:
    query: str
    k: int
    expected_types: set[str]
    matched_docs: int
    relevance_ratio: float
    retrieved_types: list[str]


@dataclass(frozen=True, slots=True)
class EvaluateRagSearchResult:
    cases: list[RagEvalCaseResult]
    average_relevance: float


class EvaluateRagSearchUseCase:
    def __init__(
            self,
            memory: MemoryInterface,
            metrics: MetricsRecorder,
            logger: logging.Logger,
            test_cases: Sequence[RagEvalTestCase],
    ) -> None:
        self._memory = memory
        self._metrics = metrics
        self._logger = logger
        self._test_cases = list(test_cases)

    async def __call__(self) -> EvaluateRagSearchResult:
        results: list[RagEvalCaseResult] = []
        total_timer = Timer.start()

        for tc in self._test_cases:
            timer = Timer.start()
            docs = await self._memory.retrieve(query=tc.query, k=tc.k)

            matched_docs, retrieved_types = self._score(tc.expected_types, docs)
            relevance_ratio = (matched_docs / tc.k) if tc.k > 0 else 0.0

            results.append(
                RagEvalCaseResult(
                    query=tc.query,
                    k=tc.k,
                    expected_types=set(tc.expected_types),
                    matched_docs=matched_docs,
                    relevance_ratio=relevance_ratio,
                    retrieved_types=retrieved_types,
                ),
            )

            self._metrics.increment(
                "memory_rag_eval_queries_total",
                1,
                tags={
                    "operation": "retrieve",
                    "expected_types": ",".join(sorted(tc.expected_types)),
                },
            )
            self._metrics.increment(
                "memory_rag_eval_docs_retrieved_total",
                len(docs),
                tags={"operation": "retrieve"},
            )
            self._metrics.increment(
                "memory_rag_eval_docs_matching_total",
                matched_docs,
                tags={"operation": "retrieve"},
            )
            self._metrics.record_duration_seconds(
                "memory_rag_eval_retrieve_duration_seconds",
                timer.elapsed_seconds,
                tags={"operation": "retrieve"},
            )

            self._logger.info(
                "rag.eval query=%r expected_types=%s k=%s matched_docs=%s relevance_ratio=%.3f retrieved_types=%s",
                tc.query,
                ",".join(sorted(tc.expected_types)),
                tc.k,
                matched_docs,
                relevance_ratio,
                retrieved_types,
            )

        average_relevance = (
            sum(r.relevance_ratio for r in results) / len(results)
            if results
            else 0.0
        )

        self._metrics.record_duration_seconds(
            "memory_rag_eval_total_duration_seconds",
            total_timer.elapsed_seconds,
            tags={"operation": "eval"},
        )
        return EvaluateRagSearchResult(cases=results, average_relevance=average_relevance)

    def _score(self, expected_types: set[str], docs: list[RetrievedDocument]) -> tuple[int, list[str]]:
        retrieved_types: list[str] = []
        matched = 0
        for d in docs:
            meta = d.metadata or {}
            doc_type = str(meta.get("type", ""))
            retrieved_types.append(doc_type)
            if doc_type and doc_type in expected_types:
                matched += 1
        return matched, retrieved_types
