from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class VectorStoreSearchResult:
    documents: list[str]
    metadatas: list[dict[str, Any]]
    ids: list[str]
    scores: list[float | None]


def _make_deterministic_id(*parts: str, length: int = 20) -> str:
    raw = "||".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]
    return f"doc_{digest}"


class VectorStore:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        backend: str = "chroma",
        persist_dir: Path,
        collection_name: str = "agent_docs",
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        if backend != "chroma":
            raise ValueError(f"Unsupported backend: {backend!r}")

        self._embedding_provider = embedding_provider
        self._backend = backend
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._metrics = metrics_recorder

        self._persist_dir.mkdir(parents=True, exist_ok=True)

        try:
            import chromadb  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "VectorStore backend 'chroma' requires package 'chromadb'. "
                "Add it to requirements and reinstall."
            ) from e

        self._chroma_client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._chroma_client.get_or_create_collection(name=self._collection_name)

    def add_documents(
        self,
        *,
        documents: Sequence[str],
        metadatas: Optional[Sequence[dict[str, Any]]] = None,
        ids: Optional[Sequence[str]] = None,
    ) -> list[str]:
        if not documents:
            return []

        if metadatas is None:
            metadatas = [{} for _ in documents]
        if len(metadatas) != len(documents):
            raise ValueError("metadatas length must match documents length")

        if ids is None:
            ids = [
                _make_deterministic_id(text, str(meta), length=20)
                for text, meta in zip(documents, metadatas)
            ]
        if len(ids) != len(documents):
            raise ValueError("ids length must match documents length")

        embeddings = self._embedding_provider.embed_documents(list(documents))
        if len(embeddings) != len(documents):
            raise ValueError("embed_documents must return embeddings for every document")

        if self._metrics is not None and embeddings:
            embedding_dim = len(embeddings[0])
            self._metrics.increment(
                "memory_embedding_dim_total",
                1,
                tags={
                    "embedding_dim": str(embedding_dim),
                    "operation": "add_documents",
                },
            )

        if hasattr(self._collection, "upsert"):
            self._collection.upsert(
                documents=list(documents),
                embeddings=embeddings,
                metadatas=list(metadatas),
                ids=list(ids),
            )
        else:
            self._collection.add(
            documents=list(documents),
            embeddings=embeddings,
            metadatas=list(metadatas),
            ids=list(ids),
            )
        return list(ids)

    def similarity_search(
        self,
        *,
        query: str,
        k: int = 5,
    ) -> VectorStoreSearchResult:
        if k <= 0:
            return VectorStoreSearchResult(documents=[], metadatas=[], ids=[], scores=[])

        query_embedding = self._embedding_provider.embed_query(query)
        if self._metrics is not None:
            embedding_dim = len(query_embedding)
            self._metrics.increment(
                "memory_embedding_dim_total",
                1,
                tags={
                    "embedding_dim": str(embedding_dim),
                    "operation": "similarity_search",
                },
            )

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=int(k),
        )

        documents = list(results.get("documents", [[]])[0] or [])
        metadatas_raw = list(results.get("metadatas", [[]])[0] or [])
        ids = list(results.get("ids", [[]])[0] or [])
        scores_raw = results.get("distances") or results.get("scores") or results.get("similarities")
        scores = list(scores_raw[0] or []) if scores_raw is not None else []

        metadatas: list[dict[str, Any]] = []
        for meta in metadatas_raw:
            metadatas.append(meta if isinstance(meta, dict) else {})

        if not scores or len(scores) != len(documents):
            scores = [None for _ in documents]

        return VectorStoreSearchResult(documents=documents, metadatas=metadatas, ids=ids, scores=scores)
