from __future__ import annotations

import hashlib
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Iterable

from agent_service.app.application.interfaces import MemoryInterface


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _chunk_text_by_words(
    text: str,
    *,
    chunk_size_words: int,
    overlap_words: int,
) -> list[str]:
    if chunk_size_words <= 0:
        return [text.strip()]

    words = text.split()
    if not words:
        return []

    chunk_size_words = max(1, chunk_size_words)
    overlap_words = max(0, overlap_words)
    if overlap_words >= chunk_size_words:
        overlap_words = max(0, chunk_size_words // 4)

    chunks: list[str] = []
    step = chunk_size_words - overlap_words
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size_words)
        chunk_words = words[start:end]
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(words):
            break
        start += step

    return chunks


def _iter_markdown_files(knowledge_dir: Path) -> Iterable[Path]:
    yield from sorted(knowledge_dir.glob("*.md"))


def _knowledge_fingerprint(knowledge_dir: Path) -> str:
    md_files = list(_iter_markdown_files(knowledge_dir))
    digests: list[str] = []
    for p in md_files:
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        digests.append(f"{p.name}:{_sha256_text(content)}")
    joined = "||".join(digests)
    return _sha256_text(joined)


@dataclass(frozen=True, slots=True)
class KnowledgeBaseIndexingConfig:
    knowledge_dir: Path
    chunk_size_words: int = 400
    overlap_words: int = 50
    flag_path: Path | None = None
    type_by_keyword: dict[str, str] = field(
        default_factory=lambda: {
            "bug": "bugs",
            "bugs": "bugs",
            "pattern": "bugs",
            "clean": "best_practice",
            "practice": "best_practice",
            "best_practice": "best_practice",
        },
    )


def _detect_doc_type(stem: str, type_by_keyword: dict[str, str]) -> str:
    stem_lower = stem.lower()
    for keyword, doc_type in type_by_keyword.items():
        if keyword in stem_lower:
            return doc_type
    return "best_practice"


async def index_knowledge_base(
    *,
    memory: MemoryInterface,
    config: KnowledgeBaseIndexingConfig,
) -> None:
    knowledge_dir = config.knowledge_dir
    if not knowledge_dir.exists():
        return

    fingerprint = _knowledge_fingerprint(knowledge_dir)
    settings_fingerprint = (
        f"chunk_size_words={config.chunk_size_words}|"
        f"overlap_words={config.overlap_words}|"
        f"type_rules={sorted(config.type_by_keyword.items())}"
    )
    fingerprint = f"{fingerprint}||{settings_fingerprint}"

    if config.flag_path is not None:
        try:
            config.flag_path.parent.mkdir(parents=True, exist_ok=True)
            if config.flag_path.exists():
                existing = config.flag_path.read_text(encoding="utf-8").strip()
                if existing == fingerprint:
                    return
        except Exception:
            pass

    for md_path in _iter_markdown_files(knowledge_dir):
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception:
            continue

        doc_hash = _sha256_text(text)
        source = md_path.name
        doc_type = _detect_doc_type(md_path.stem, config.type_by_keyword)

        chunks = _chunk_text_by_words(
            text,
            chunk_size_words=config.chunk_size_words,
            overlap_words=config.overlap_words,
        )
        for idx, chunk in enumerate(chunks):
            chunk_id = f"kb_{md_path.stem}_{doc_hash[:12]}_{idx}"
            await memory.save_document(
                chunk,
                metadata={
                    "id": chunk_id,
                    "source": source,
                    "type": doc_type,
                    "doc": md_path.stem,
                    "chunk_idx": idx,
                    "doc_hash": doc_hash,
                },
            )

    if config.flag_path is not None:
        try:
            config.flag_path.write_text(fingerprint, encoding="utf-8")
        except Exception:
            pass
