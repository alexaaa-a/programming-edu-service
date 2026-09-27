import hashlib
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence


Vector = list[float]

_MAX_CHARS = 6000
_BATCH_SIZE = 32


class EmbeddingBackend(Protocol):
    name: str

    async def embed_batch(self, texts: list[str]) -> list[Vector]: ...


@dataclass(frozen=True, slots=True)
class HashEmbeddingBackend:
    dimension: int = 256
    salt: str = "agent-service"
    name: str = "hash256"

    def _embed_one(self, text: str) -> Vector:
        data = bytearray()
        for i in range(64):
            digest = hashlib.sha256(f"{self.salt}||{text}||{i}".encode("utf-8")).digest()
            data.extend(digest)
            if len(data) >= self.dimension:
                break
        return [b / 255.0 for b in data[: self.dimension]]

    async def embed_batch(self, texts: list[str]) -> list[Vector]:
        return [self._embed_one(text) for text in texts]


class OpenAIEmbeddingBackend:
    def __init__(
            self,
            client: Any,
            model: str,
            logger: logging.Logger | None = None,
            cache_size: int = 256,
    ) -> None:
        self._client = client
        self._model = model
        self._logger = logger or logging.getLogger("agent_service")
        self._cache: OrderedDict[str, Vector] = OrderedDict()
        self._cache_size = max(16, cache_size)
        self.name = f"openai_{_slug(model)}"

    async def embed_batch(self, texts: list[str]) -> list[Vector]:
        prepared = [_clip(text) for text in texts]
        vectors: list[Vector | None] = [None] * len(prepared)
        missing: list[tuple[int, str]] = []
        for idx, text in enumerate(prepared):
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                vectors[idx] = cached
            else:
                missing.append((idx, text))

        for start in range(0, len(missing), _BATCH_SIZE):
            chunk = missing[start : start + _BATCH_SIZE]
            payload = [text for _, text in chunk]
            response = await self._client.embeddings.create(model=self._model, input=payload)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(payload):
                raise RuntimeError("OpenAI embeddings returned unexpected batch size")
            for (idx, text), item in zip(chunk, ordered):
                vector = list(item.embedding)
                self._remember(text, vector)
                vectors[idx] = vector

        return [item for item in vectors if item is not None]

    def _remember(self, text: str, vector: Vector) -> None:
        self._cache[text] = vector
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


@dataclass
class EmbeddingService:
    backend: EmbeddingBackend
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.name = self.backend.name

    async def embed(self, text: str) -> Vector:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[Vector]:
        if not texts:
            return []
        return await self.backend.embed_batch(texts)

    async def embed_query(self, text: str) -> Vector:
        return await self.embed(text)

    async def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return await self.embed_batch(list(texts))


def build_embedding_service(
        backend: str,
        client: Any,
        model: str,
        logger: logging.Logger | None = None,
) -> EmbeddingService:
    kind = (backend or "openai").strip().lower()
    if kind == "hash":
        return EmbeddingService(HashEmbeddingBackend())
    if client is None:
        raise ValueError("OpenAI embedding backend requires an AsyncOpenAI client")
    return EmbeddingService(OpenAIEmbeddingBackend(client, model=model, logger=logger))


def _clip(text: str) -> str:
    text = text.strip() or " "
    if len(text) <= _MAX_CHARS:
        return text
    return text[:_MAX_CHARS]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug[:40] or "emb"
