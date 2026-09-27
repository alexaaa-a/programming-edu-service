import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


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


def chroma_where(types: set[str] | None) -> dict[str, Any] | None:
    if not types:
        return None
    values = sorted(str(item) for item in types)
    if len(values) == 1:
        return {"type": values[0]}
    return {"$or": [{"type": value} for value in values]}


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, str | int | float | bool]:
    clean: dict[str, str | int | float | bool] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean[str(key)] = value
        elif isinstance(value, int):
            clean[str(key)] = value
        elif isinstance(value, float):
            clean[str(key)] = value
        else:
            clean[str(key)] = str(value)
    return clean


class VectorStore:
    def __init__(
            self,
            embedding_provider: EmbeddingProvider,
            persist_dir: Path,
            collection_name: str,
            metrics_recorder: MetricsRecorder | None = None,
            chroma_client: Any | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        self._metrics = metrics_recorder

        self._persist_dir.mkdir(parents=True, exist_ok=True)

        if chroma_client is None:
            try:
                import chromadb
            except ImportError as e:
                raise RuntimeError(
                    "VectorStore requires package 'chromadb'. Add it to requirements and reinstall."
                ) from e
            chroma_client = chromadb.PersistentClient(path=str(self._persist_dir))

        self._chroma_client = chroma_client
        self._collection = self._chroma_client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def add_documents(
            self,
            documents: Sequence[str],
            metadatas: Optional[Sequence[dict[str, Any]]] = None,
            ids: Optional[Sequence[str]] = None,
    ) -> list[str]:
        if not documents:
            return []

        if metadatas is None:
            cleaned = [{} for _ in documents]
        else:
            if len(metadatas) != len(documents):
                raise ValueError("metadatas length must match documents length")
            cleaned = [sanitize_metadata(item) for item in metadatas]

        if ids is None:
            ids = [
                _make_deterministic_id(text, str(meta), length=20)
                for text, meta in zip(documents, cleaned)
            ]
        if len(ids) != len(documents):
            raise ValueError("ids length must match documents length")

        embeddings = await self._embedding_provider.embed_documents(list(documents))
        if len(embeddings) != len(documents):
            raise ValueError("embed_documents must return embeddings for every document")

        if self._metrics is not None and embeddings:
            self._metrics.increment(
                "memory_embedding_dim_total",
                1,
                tags={
                    "embedding_dim": str(len(embeddings[0])),
                    "operation": "add_documents",
                    "collection": self._collection_name,
                },
            )

        payload = {
            "documents": list(documents),
            "embeddings": embeddings,
            "metadatas": cleaned,
            "ids": list(ids),
        }
        if hasattr(self._collection, "upsert"):
            self._collection.upsert(**payload)
        else:
            self._collection.add(**payload)
        return list(ids)

    async def similarity_search(
            self,
            query: str,
            k: int = 5,
            where: dict[str, Any] | None = None,
            query_embedding: list[float] | None = None,
    ) -> VectorStoreSearchResult:
        if k <= 0:
            return VectorStoreSearchResult(documents=[], metadatas=[], ids=[], scores=[])

        if query_embedding is None:
            query_embedding = await self._embedding_provider.embed_query(query)
        if self._metrics is not None:
            self._metrics.increment(
                "memory_embedding_dim_total",
                1,
                tags={
                    "embedding_dim": str(len(query_embedding)),
                    "operation": "similarity_search",
                    "collection": self._collection_name,
                },
            )

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": int(k),
        }
        if where:
            kwargs["where"] = where

        try:
            results = self._collection.query(**kwargs)
        except Exception:
            return VectorStoreSearchResult(documents=[], metadatas=[], ids=[], scores=[])

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
