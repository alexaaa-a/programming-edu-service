from __future__ import annotations

from pathlib import Path
import hashlib
import logging
from typing import Any, Protocol

from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.interfaces import ChatHistoryRepository
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.infrastructure.memory.embedding_service import EmbeddingService
from agent_service.app.infrastructure.memory.vector_store import VectorStore
from agent_service.app.infrastructure.observability.timer import Timer
from agent_service.app.application.observability.tracing import get_trace_id


class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[RetrievedDocument]) -> list[RetrievedDocument]: ...


class RagMemory(MemoryInterface):
    def __init__(
        self,
        knowledge_dir: Path | None = None,
        *,
        vector_store: VectorStore | None = None,
        reranker: Reranker | None = None,
        chat_history_repository: ChatHistoryRepository,
        metrics_recorder: MetricsRecorder | None = None,
        logger: logging.Logger | None = None,
        max_retrieve_top_k: int = 5,
    ) -> None:
        if knowledge_dir is None:
            knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge"

        self._knowledge_dir = knowledge_dir
        self._metrics = metrics_recorder

        if vector_store is None:
            persist_dir = Path(__file__).resolve().parents[1] / "vector_store_data"
            vector_store = VectorStore(
                embedding_provider=EmbeddingService(),
                backend="chroma",
                persist_dir=persist_dir,
                collection_name="agent_docs",
                metrics_recorder=metrics_recorder,
            )
        self._vector_store = vector_store
        self._reranker = reranker
        self._chat_history_repository = chat_history_repository
        self._max_retrieve_top_k = max_retrieve_top_k
        self._logger = logger

    async def retrieve(
        self,
        query: str,
        k: int,
        types: set[str] | None = None,
    ) -> list[RetrievedDocument]:
        async def _impl() -> list[RetrievedDocument]:
            timer = Timer.start()
            effective_k = min(max(int(k), 0), self._max_retrieve_top_k)
            query_len = len(query)
            fallback_used = False
            result = self._vector_store.similarity_search(query=query, k=effective_k)
            docs: list[RetrievedDocument] = []
            for text, meta, score in zip(result.documents, result.metadatas, result.scores):
                docs.append(RetrievedDocument(text=text, metadata=meta, score=score))

            if not docs:
                if self._metrics is not None:
                    self._metrics.record_duration_seconds(
                        "memory_retrieve_duration_seconds",
                        timer.elapsed_seconds,
                        tags={"operation": "retrieve"},
                    )
                    self._metrics.increment(
                        "memory_retrieve_found_documents_total",
                        0,
                        tags={"operation": "retrieve"},
                    )
                return []

            unfiltered_docs = docs
            if types:
                type_set = {str(t) for t in types}
                filtered = [
                    d
                    for d in unfiltered_docs
                    if str((d.metadata or {}).get("type", "")) in type_set
                ]
                if filtered:
                    docs = filtered
                else:
                    docs = unfiltered_docs
                    fallback_used = True

            if self._reranker is None:
                final_docs = docs
            else:
                final_docs = await self._reranker.rerank(query=query, candidates=docs)

            if self._metrics is not None:
                self._metrics.increment(
                    "memory_retrieve_requests_total",
                    1,
                    tags={"operation": "retrieve"},
                )
                self._metrics.record_duration_seconds(
                    "memory_retrieve_duration_seconds",
                    timer.elapsed_seconds,
                    tags={"operation": "retrieve"},
                )
                self._metrics.increment(
                    "memory_retrieve_found_documents_total",
                    len(final_docs),
                    tags={"operation": "retrieve"},
                )

            if self._logger is not None:
                self._logger.info(
                    "memory.retrieve.summary trace_id=%s k=%s effective_k=%s types=%s fallback_used=%s reranker_used=%s found_docs=%s query_len=%s duration_seconds=%.6f",
                    get_trace_id(),
                    k,
                    effective_k,
                    ",".join(sorted(types)) if types else None,
                    fallback_used,
                    self._reranker is not None,
                    len(final_docs),
                    query_len,
                    timer.elapsed_seconds,
                )

            return final_docs

        return await _impl()

    async def save_document(self, text: str, metadata: dict) -> None:
        doc_id = None
        if metadata:
            doc_id = (
                metadata.get("id")
                or metadata.get("doc_id")
                or metadata.get("key")
                or metadata.get("name")
            )
        if not doc_id:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            doc_id = f"sha_{digest}"

        self._vector_store.add_documents(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[str(doc_id)],
        )

    async def get_chat_history(self, session_id: str) -> list[Any]:
        return await self._chat_history_repository.get_history(session_id)

    async def append_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        await self._chat_history_repository.append_message(
            session_id=session_id,
            role=role,
            content=content,
        )
