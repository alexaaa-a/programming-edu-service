import logging
import hashlib
import json
from typing import Any

from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.interfaces.retrieve_cache import RetrieveCache
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.metrics import instrument_async
from agent_service.app.application.observability.tracing import get_trace_id


class CachedMemory(MemoryInterface):
    def __init__(
            self,
            inner: MemoryInterface,
            retrieve_cache: RetrieveCache,
            ttl_sec: int,
            cache_version: str = "v1",
            logger: logging.Logger | None = None,
            metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        self._inner = inner
        self._cache = retrieve_cache
        self._ttl_sec = ttl_sec
        self._cache_version = cache_version
        self._logger = logger
        self._metrics = metrics_recorder

    async def retrieve(
            self,
            query: str,
            k: int,
            types: set[str] | None = None,
    ) -> list[RetrievedDocument]:
        async def _impl() -> list[RetrievedDocument]:
            if self._ttl_sec <= 0:
                return await self._inner.retrieve(query=query, k=k, types=types)

            generation = "0"
            try:
                generation = await self._cache.generation()
            except Exception:
                generation = "0"
            key_payload: dict[str, Any] = {
                "q": query,
                "k": int(k),
                "types": sorted(map(str, types)) if types else None,
                "v": self._cache_version,
                "g": generation,
            }
            key_raw = json.dumps(key_payload, ensure_ascii=False, default=str)
            key = "rag_retrieve:" + hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

            cached = await self._cache.get(key)
            if cached is not None:
                if self._logger is not None:
                    self._logger.info(
                        "memory.retrieve.cache_hit trace_id=%s key=%s query_len=%s k=%s types=%s",
                        get_trace_id(),
                        key[:12],
                        len(query),
                        int(k),
                        ",".join(sorted(types)) if types else None,
                    )
                return cached

            if self._logger is not None:
                self._logger.info(
                    "memory.retrieve.cache_miss trace_id=%s key=%s query_len=%s k=%s types=%s",
                    get_trace_id(),
                    key[:12],
                    len(query),
                    int(k),
                    ",".join(sorted(types)) if types else None,
                )
            value = await self._inner.retrieve(query=query, k=k, types=types)
            await self._cache.set(key, value, ttl_sec=self._ttl_sec)
            return value

        if self._metrics is None:
            return await _impl()

        decorated = instrument_async(
            self._metrics,
            component="retrieve",
            operation="retrieve",
            tags={"cache": "redis" if self._ttl_sec > 0 else "none"},
            logger=self._logger,
            log_success=False,
            log_error=True,
        )(_impl)
        return await decorated()

    async def save_document(self, text: str, metadata: dict) -> None:
        await self._inner.save_document(text=text, metadata=metadata)
        try:
            await self._cache.bump_generation()
        except Exception:
            if self._logger is not None:
                self._logger.exception("memory.cache.bump_failed")

    async def get_chat_history(self, session_id: str) -> list[Any]:
        return await self._inner.get_chat_history(session_id=session_id)

    async def append_chat_message(
            self,
            session_id: str,
            role: str,
            content: str,
            turn_id: str | None = None,
    ) -> None:
        await self._inner.append_chat_message(
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
        rollback = getattr(self._inner, "rollback_last_chat_message", None)
        if rollback is None:
            return
        await rollback(session_id=session_id, role=role, content=content)
