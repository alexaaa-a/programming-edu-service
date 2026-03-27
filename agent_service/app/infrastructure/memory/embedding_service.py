from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, Sequence


Vector = list[float]


class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> Vector: ...

    def embed_batch(self, texts: list[str]) -> list[Vector]: ...


@dataclass(frozen=True, slots=True)
class HashEmbeddingBackend:
    dimension: int = 256
    salt: str = "agent-service"

    def _embed_one(self, text: str) -> Vector:
        data = bytearray()
        for i in range(0, 64):
            h = hashlib.sha256((self.salt + "||" + text + "||" + str(i)).encode("utf-8")).digest()
            data.extend(h)
            if len(data) >= self.dimension:
                break

        vec = [(b / 255.0) for b in data[: self.dimension]]
        return vec

    def embed(self, text: str) -> Vector:
        return self._embed_one(text)

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        return [self._embed_one(t) for t in texts]


@dataclass(frozen=True, slots=True)
class EmbeddingService:
    backend: EmbeddingBackend = HashEmbeddingBackend()

    def embed(self, text: str) -> Vector:
        return self.backend.embed(text)

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        return self.backend.embed_batch(texts)

    def embed_query(self, text: str) -> Vector:
        return self.embed(text)

    def embed_documents(self, texts: Sequence[str]) -> list[Vector]:
        return self.embed_batch(list(texts))
