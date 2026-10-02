import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from agent_service.app.application.decisions.policies import (
    MEMORY_KEEP_THRESHOLD,
    memory_keep_question,
    memory_keep_state,
    rerank_questions,
    rerank_state,
)
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import ChatHistoryRepository, MemoryInterface
from agent_service.app.application.interfaces.decisions import DecisionModelInterface
from agent_service.app.application.memory.layers import (
    SEMANTIC,
    VECTOR_LAYERS,
    layer_for_type,
    layers_for_types,
    scope_filter,
    types_for_layer,
)
from agent_service.app.application.memory.provenance import (
    is_fresh,
    merged_metadata,
    prepare_memory_write,
    reinforced_metadata,
    usefulness_multiplier,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.tracing import get_trace_id
from agent_service.app.application.observability.llm_trace import LlmTracer, clip_for_trace, get_noop_tracer
from agent_service.app.infrastructure.memory.embedding_service import EmbeddingService
from agent_service.app.infrastructure.memory.vector_store import VectorStore, chroma_where
from agent_service.app.infrastructure.observability.timer import Timer


_RRF_K = 60
_DEDUP_TYPES = frozenset({"chat_episode", "best_practice", "bugs"})
_GATED_TYPES = frozenset({"chat_episode"})


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
            decisions: DecisionModelInterface | None = None,
            min_confidence: float = 0.6,
            dedup_similarity: float = 0.92,
            rerank_enabled: bool = True,
            write_gate_enabled: bool = True,
            reinforce_enabled: bool = True,
    ) -> None:
        self._stores = stores
        self._embeddings = embeddings
        self._chat_history_repository = chat_history_repository
        self._metrics = metrics_recorder
        self._logger = logger
        self._max_retrieve_top_k = max_retrieve_top_k
        self._tracer = tracer or get_noop_tracer()
        self._decisions = decisions
        self._min_confidence = min_confidence
        self._dedup_similarity = dedup_similarity
        self._rerank_enabled = rerank_enabled
        self._write_gate_enabled = write_gate_enabled
        self._reinforce_enabled = reinforce_enabled

    @property
    def _decisions_on(self) -> bool:
        return self._decisions is not None and self._decisions.enabled

    async def retrieve(
            self,
            query: str,
            k: int,
            types: set[str] | None = None,
            scope: Mapping[str, str] | None = None,
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
                "scoped": bool(scope),
            },
        ) as obs:
            result = await self._retrieve_layers(query, effective_k, types, scope)
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
            scope: Mapping[str, str] | None = None,
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
                    scope=scope,
                )
                for name in layer_names
            ]
        )
        merged = _rrf_merge(list(zip(layer_names, buckets)), limit=max(effective_k * 3, effective_k))
        fresh = [doc for doc in merged if is_fresh(doc.metadata)]
        dropped = len(merged) - len(fresh)
        result, reranked = await self._rerank(query, fresh, effective_k)

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
                "stale_dropped=%s reranked=%s scoped=%s query_len=%s duration_seconds=%.4f",
                get_trace_id(),
                ",".join(layer_names),
                ",".join(sorted(type_set)) if type_set else None,
                effective_k,
                len(result),
                dropped,
                reranked,
                ",".join(sorted(scope_filter(type_set, scope))) or "-",
                len(query),
                timer.elapsed_seconds,
            )
        return result

    async def _rerank(
            self,
            query: str,
            docs: list[RetrievedDocument],
            k: int,
    ) -> tuple[list[RetrievedDocument], bool]:
        if not self._rerank_enabled or not self._decisions_on or len(docs) < 2:
            return docs[:k], False
        candidates = docs[: max(k * 2, k)]
        answers = await self._decisions.ask(
            rerank_state(query, [doc.text for doc in candidates]),
            rerank_questions(len(candidates)),
            label="memory_rerank",
        )
        if not answers:
            return docs[:k], False

        scored: list[tuple[float, RetrievedDocument]] = []
        irrelevant = 0
        for index, doc in enumerate(candidates):
            answer = answers.score(f"doc_{index}", min_confidence=self._min_confidence)
            if answer is None:
                scored.append((0.5, doc))
                continue
            if answer.level == 0:
                irrelevant += 1
                continue
            scored.append((answer.normalized, doc))
        if not scored:
            return docs[:k], False
        scored.sort(key=lambda item: item[0], reverse=True)
        if self._metrics is not None and irrelevant:
            self._metrics.increment(
                "memory_rerank_dropped_total",
                irrelevant,
                tags={"operation": "rerank"},
            )
        return [doc for _, doc in scored[:k]], True

    async def reinforce(self, documents: list[RetrievedDocument]) -> int:
        if not self._reinforce_enabled or not documents:
            return 0
        by_layer: dict[str, tuple[list[str], list[dict[str, Any]]]] = {}
        for doc in documents:
            meta = dict(doc.metadata or {})
            doc_id = str(meta.get("id") or "").strip()
            if not doc_id:
                continue
            layer = str(meta.get("layer") or layer_for_type(meta.get("type")))
            if layer not in self._stores:
                continue
            ids, metas = by_layer.setdefault(layer, ([], []))
            ids.append(doc_id)
            metas.append(reinforced_metadata(meta))

        updated = 0
        for layer, (ids, metas) in by_layer.items():
            try:
                updated += await self._stores[layer].update_metadata(ids, metas)
            except Exception:
                if self._logger is not None:
                    self._logger.exception("memory.reinforce.failed layer=%s", layer)
        if updated and self._metrics is not None:
            self._metrics.increment(
                "memory_reinforced_documents_total",
                updated,
                tags={"operation": "reinforce"},
            )
        if updated and self._logger is not None:
            self._logger.info(
                "memory.reinforce trace_id=%s documents=%s",
                get_trace_id(),
                updated,
            )
        return updated

    async def save_document(self, text: str, metadata: dict) -> None:
        decision = prepare_memory_write(text, metadata)
        if not decision.accept:
            self._reject(decision.metadata.get("type"), decision.reason or "unknown", len(text or ""))
            return

        meta = dict(decision.metadata)
        doc_type = str(meta.get("type") or "best_practice")
        if doc_type == "student_note":
            self._reject(doc_type, "student_note_not_vector", len(decision.text))
            return
        layer = layer_for_type(doc_type)
        store = self._stores.get(layer)
        if store is None:
            store = self._stores[SEMANTIC]
            layer = SEMANTIC
        meta["type"] = doc_type
        meta["layer"] = layer
        meta.setdefault("saved_at", datetime.now(tz=timezone.utc).isoformat())

        if not await self._worth_keeping(decision.text, meta):
            self._reject(doc_type, "low_value", len(decision.text))
            return

        doc_id = meta.get("id") or meta.get("doc_id") or meta.get("key") or meta.get("name")
        if not doc_id:
            digest = hashlib.sha256(decision.text.encode("utf-8")).hexdigest()[:16]
            doc_id = f"sha_{digest}"
        doc_id = str(doc_id)

        duplicate = await self._find_duplicate(store, decision.text, meta)
        if duplicate is not None:
            duplicate_id, previous = duplicate
            doc_id = duplicate_id
            meta = merged_metadata(previous, meta)
            if self._metrics is not None:
                self._metrics.increment(
                    "memory_save_merged_total",
                    1,
                    tags={"type": doc_type, "layer": layer},
                )
        meta["id"] = doc_id

        await store.add_documents(documents=[decision.text], metadatas=[meta], ids=[doc_id])
        if self._logger is not None:
            self._logger.info(
                "memory.save.layered trace_id=%s layer=%s type=%s id=%s chars=%s "
                "source=%s writer=%s verified=%s merges=%s",
                get_trace_id(),
                layer,
                doc_type,
                doc_id,
                len(decision.text),
                meta.get("source"),
                meta.get("writer"),
                meta.get("verified"),
                meta.get("merges", 0),
            )

    async def _worth_keeping(self, text: str, meta: Mapping[str, Any]) -> bool:
        doc_type = str(meta.get("type") or "")
        if doc_type not in _GATED_TYPES:
            return True
        if not self._write_gate_enabled or not self._decisions_on:
            return True
        answers = await self._decisions.ask(
            memory_keep_state(text, meta),
            [memory_keep_question(doc_type)],
            label="memory_write_gate",
        )
        probability = answers.noul("keep")
        if probability is None:
            return True
        if probability >= MEMORY_KEEP_THRESHOLD:
            return True
        if self._logger is not None:
            self._logger.info(
                "memory.save.low_value trace_id=%s type=%s p_keep=%.3f",
                get_trace_id(),
                doc_type,
                probability,
            )
        return False

    async def _find_duplicate(
            self,
            store: VectorStore,
            text: str,
            meta: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any]] | None:
        doc_type = str(meta.get("type") or "")
        if doc_type not in _DEDUP_TYPES or self._dedup_similarity >= 1.0:
            return None
        scope = {
            key: str(meta[key])
            for key in ("user_id", "session_id")
            if str(meta.get(key) or "").strip()
        }
        try:
            found = await store.similarity_search(
                query=text,
                k=1,
                where=chroma_where({doc_type}, scope or None),
            )
        except Exception:
            return None
        if not found.ids or not found.scores:
            return None
        distance = found.scores[0]
        if distance is None:
            return None
        if float(distance) > (1.0 - self._dedup_similarity):
            return None
        previous = found.metadatas[0] if found.metadatas else {}
        return str(found.ids[0]), dict(previous or {})

    def _reject(self, doc_type: Any, reason: str, chars: int) -> None:
        if self._logger is not None:
            self._logger.info(
                "memory.save.rejected trace_id=%s type=%s reason=%s chars=%s",
                get_trace_id(),
                doc_type,
                reason,
                chars,
            )
        if self._metrics is not None:
            self._metrics.increment("memory_save_rejected_total", 1, tags={"reason": reason})

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
            scope: Mapping[str, str] | None = None,
    ) -> list[RetrievedDocument]:
        store = self._stores.get(layer)
        if store is None:
            return []
        if types is not None and not types:
            return []
        try:
            result = await store.similarity_search(
                query=query,
                k=k,
                where=chroma_where(types, scope_filter(types, scope) or None),
                query_embedding=query_embedding,
            )
        except Exception:
            if self._logger is not None:
                self._logger.exception("memory.layer.search_failed layer=%s", layer)
            return []

        docs: list[RetrievedDocument] = []
        ids = list(result.ids) + [""] * max(len(result.documents) - len(result.ids), 0)
        for text, meta, score, doc_id in zip(result.documents, result.metadatas, result.scores, ids):
            metadata = dict(meta or {})
            metadata.setdefault("layer", layer)
            if doc_id and not str(metadata.get("id") or "").strip():
                metadata["id"] = doc_id
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
            fused[key] = fused.get(key, 0.0) + (1.0 / (_RRF_K + rank)) * usefulness_multiplier(doc.metadata)
            if key not in chosen:
                chosen[key] = doc
    ranked = sorted(chosen, key=lambda key: fused[key], reverse=True)
    return [chosen[key] for key in ranked[:limit]]
