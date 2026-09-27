import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import ChatHistoryRepository, MemoryInterface
from agent_service.app.application.memory.layers import (
    SEMANTIC,
    VECTOR_LAYERS,
    layer_for_type,
    layers_for_types,
    types_for_layer,
)
from agent_service.app.application.memory.provenance import (
    is_fresh,
    prepare_memory_write,
    recency_multiplier,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id
from agent_service.app.application.observability.llm_trace import LlmTracer, clip_for_trace, get_noop_tracer
from agent_service.app.infrastructure.memory.embedding_service import EmbeddingService
from agent_service.app.infrastructure.memory.vector_store import VectorStore, chroma_where
from agent_service.app.infrastructure.observability.timer import Timer


_RRF_K = 60


class LayeredMemory(MemoryInterface):
    def __init__(
            self,
            stores: dict[str, VectorStore],
            embeddings: EmbeddingService,
            chat_history_repository: ChatHistoryRepository,
            metrics_recorder: MetricsRecorder | None = None,
            logger: logging.Logger | None = None,
            max_retrieve_top_k: int = 8,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._stores = stores
        self._embeddings = embeddings
        self._chat_history_repository = chat_history_repository
        self._metrics = metrics_recorder
        self._logger = logger
        self._max_retrieve_top_k = max_retrieve_top_k
        self._tracer = tracer or get_noop_tracer()

    async def retrieve(
            self,
            query: str,
            k: int,
            types: set[str] | None = None,
    ) -> list[RetrievedDocument]:
        effective_k = min(max(int(k), 0), self._max_retrieve_top_k)
        if effective_k == 0 or not query.strip():
            return []

        with self._tracer.observation(
            "memory.retrieve",
            as_type="retriever",
            input={"query": clip_for_trace(query, max_chars=800), "k": effective_k},
            metadata={
                "types": ",".join(sorted(str(item) for item in types)) if types else None,
            },
        ) as obs:
            result = await self._retrieve_layers(query, effective_k, types)
            obs.update(
                output=[
                    {
                        "chars": len(doc.text or ""),
                        "score": doc.score,
                        "type": (doc.metadata or {}).get("type"),
                        "source": (doc.metadata or {}).get("source"),
                    }
                    for doc in result
                ],
                metadata={"found": len(result)},
            )
            return result

    async def _retrieve_layers(
            self,
            query: str,
            effective_k: int,
            types: set[str] | None,
    ) -> list[RetrievedDocument]:
        timer = Timer.start()
        type_set = {str(item) for item in types} if types else None
        layer_names = layers_for_types(type_set)
        query_embedding = await self._embeddings.embed_query(query)
        per_layer_k = min(self._max_retrieve_top_k, max(effective_k, 4))

        buckets = await asyncio.gather(
            *[
                self._search_layer(
                    layer=name,
                    query=query,
                    k=per_layer_k,
                    types=types_for_layer(name, type_set),
                    query_embedding=query_embedding,
                )
                for name in layer_names
            ]
        )
        merged = _rrf_merge(list(zip(layer_names, buckets)), limit=max(effective_k * 3, effective_k))
        fresh = [doc for doc in merged if is_fresh(doc.metadata)]
        dropped = len(merged) - len(fresh)
        result = fresh[:effective_k]

        if self._metrics is not None:
            self._metrics.increment("memory_retrieve_requests_total", 1, tags={"operation": "retrieve"})
            self._metrics.record_duration_seconds(
                "memory_retrieve_duration_seconds",
                timer.elapsed_seconds,
                tags={"operation": "retrieve"},
            )
            self._metrics.increment(
                "memory_retrieve_found_documents_total",
                len(result),
                tags={"operation": "retrieve"},
            )
            if dropped:
                self._metrics.increment(
                    "memory_retrieve_stale_dropped_total",
                    dropped,
                    tags={"operation": "retrieve"},
                )
        if self._logger is not None:
            self._logger.info(
                "memory.retrieve.layered trace_id=%s layers=%s types=%s k=%s found=%s "
                "stale_dropped=%s query_len=%s duration_seconds=%.4f",
                get_trace_id(),
                ",".join(layer_names),
                ",".join(sorted(type_set)) if type_set else None,
                effective_k,
                len(result),
                dropped,
                len(query),
                timer.elapsed_seconds,
            )
        return result

    async def save_document(self, text: str, metadata: dict) -> None:
        decision = prepare_memory_write(text, metadata)
        if not decision.accept:
            if self._logger is not None:
                self._logger.info(
                    "memory.save.rejected trace_id=%s type=%s reason=%s chars=%s",
                    get_trace_id(),
                    decision.metadata.get("type"),
                    decision.reason,
                    len(text or ""),
                )
            if self._metrics is not None:
                self._metrics.increment(
                    "memory_save_rejected_total",
                    1,
                    tags={"reason": decision.reason or "unknown"},
                )
            return

        meta = dict(decision.metadata)
        doc_type = str(meta.get("type") or "best_practice")
        layer = layer_for_type(doc_type)
        store = self._stores.get(layer)
        if store is None:
            store = self._stores[SEMANTIC]
            layer = SEMANTIC
        meta["type"] = doc_type
        meta["layer"] = layer
        meta.setdefault("saved_at", datetime.now(tz=timezone.utc).isoformat())

        doc_id = meta.get("id") or meta.get("doc_id") or meta.get("key") or meta.get("name")
        if not doc_id:
            digest = hashlib.sha256(decision.text.encode("utf-8")).hexdigest()[:16]
            doc_id = f"sha_{digest}"

        await store.add_documents(documents=[decision.text], metadatas=[meta], ids=[str(doc_id)])
        if self._logger is not None:
            self._logger.info(
                "memory.save.layered trace_id=%s layer=%s type=%s id=%s chars=%s "
                "source=%s writer=%s verified=%s",
                get_trace_id(),
                layer,
                doc_type,
                doc_id,
                len(decision.text),
                meta.get("source"),
                meta.get("writer"),
                meta.get("verified"),
            )

    async def get_chat_history(self, session_id: str) -> list[Any]:
        return await self._chat_history_repository.get_history(session_id)

    async def append_chat_message(
            self,
            session_id: str,
            role: str,
            content: str,
            turn_id: str | None = None,
    ) -> None:
        await self._chat_history_repository.append_message(
            session_id=session_id,
            role=role,
            content=content,
            turn_id=turn_id,
        )

    async def rollback_last_chat_message(
            self,
            session_id: str,
            role: str,
            content: str,
    ) -> None:
        rollback = getattr(self._chat_history_repository, "rollback_last_message", None)
        if rollback is None:
            return
        await rollback(session_id=session_id, role=role, content=content)

    async def _search_layer(
            self,
            layer: str,
            query: str,
            k: int,
            types: set[str] | None,
            query_embedding: list[float],
    ) -> list[RetrievedDocument]:
        store = self._stores.get(layer)
        if store is None:
            return []
        try:
            result = await store.similarity_search(
                query=query,
                k=k,
                where=chroma_where(types),
                query_embedding=query_embedding,
            )
        except Exception:
            if self._logger is not None:
                self._logger.exception("memory.layer.search_failed layer=%s", layer)
            return []

        docs: list[RetrievedDocument] = []
        for text, meta, score in zip(result.documents, result.metadatas, result.scores):
            metadata = dict(meta or {})
            metadata.setdefault("layer", layer)
            docs.append(RetrievedDocument(text=text, metadata=metadata, score=score))
        return docs


def build_layered_stores(
        embeddings: EmbeddingService,
        persist_dir: Path,
        metrics_recorder: MetricsRecorder | None = None,
) -> dict[str, VectorStore]:
    persist_dir.mkdir(parents=True, exist_ok=True)
    try:
        import chromadb
    except ImportError as e:
        raise RuntimeError("LayeredMemory requires package 'chromadb'.") from e
    client = chromadb.PersistentClient(path=str(persist_dir))
    stores: dict[str, VectorStore] = {}
    for layer in VECTOR_LAYERS:
        stores[layer] = VectorStore(
            embedding_provider=embeddings,
            persist_dir=persist_dir,
            collection_name=_collection_name(layer, embeddings.name),
            metrics_recorder=metrics_recorder,
            chroma_client=client,
        )
    return stores


def _collection_name(layer: str, embedding_name: str) -> str:
    raw = f"{layer}_{embedding_name}"
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", raw).strip("._-")
    return (slug or layer)[:63]


def _rrf_merge(
        buckets: list[tuple[str, list[RetrievedDocument]]],
        limit: int,
) -> list[RetrievedDocument]:
    fused: dict[str, float] = {}
    chosen: dict[str, RetrievedDocument] = {}
    for layer, docs in buckets:
        for rank, doc in enumerate(docs, start=1):
            key = str((doc.metadata or {}).get("id") or "") or f"{layer}:{hash(doc.text)}"
            fused[key] = fused.get(key, 0.0) + (1.0 / (_RRF_K + rank)) * recency_multiplier(doc.metadata)
            if key not in chosen:
                chosen[key] = doc
    ranked = sorted(chosen, key=lambda key: fused[key], reverse=True)
    return [chosen[key] for key in ranked[:limit]]
