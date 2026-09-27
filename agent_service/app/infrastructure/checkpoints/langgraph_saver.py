import asyncio
import base64
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from agent_service.app.application.dto.chat import ChatTurnResult, PathStepResult as ChatPathStep
from agent_service.app.application.dto.review import (
    ChallengeResult,
    CriterionResult,
    PathStepResult,
    Review,
)
from agent_service.app.application.interfaces.run_checkpoint_store import RunCheckpointStore
from agent_service.app.application.review.acceptance import (
    AcceptanceCriterion,
    AcceptanceRubric,
    CriterionCheck,
)
from agent_service.app.application.review.adversarial import ChallengeVerdict
from agent_service.app.application.review.agent_path import AgentPath, PathStep, PathVerdict
from agent_service.app.application.review.draft_select import DraftScore, SelectedDraft
from agent_service.app.application.review.scorecard import ScoreCard
from agent_service.app.application.team import TeamMember
from agent_service.app.application.team_router import RouteDecision
from agent_service.app.application.tools.models import ToolFinding, ToolReport

_FORMAT = "lgckpt-v2"
_logger = logging.getLogger(__name__)

_MSGPACK_ALLOWLIST: tuple[type, ...] = (
    Review,
    CriterionResult,
    ChallengeResult,
    PathStepResult,
    ChatTurnResult,
    ChatPathStep,
    AgentPath,
    PathStep,
    PathVerdict,
    AcceptanceCriterion,
    AcceptanceRubric,
    CriterionCheck,
    ChallengeVerdict,
    ScoreCard,
    DraftScore,
    SelectedDraft,
    ToolReport,
    ToolFinding,
    TeamMember,
    RouteDecision,
)


def _checkpoint_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_MSGPACK_ALLOWLIST)


def _encode_typed(value: tuple[str, bytes]) -> list[str]:
    type_name, payload = value
    return [str(type_name), base64.b64encode(payload).decode("ascii")]


def _decode_typed(value: Any) -> tuple[str, bytes]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("typed payload must be [type, base64_bytes]")
    type_name, encoded = value
    if not isinstance(type_name, str) or not isinstance(encoded, str):
        raise ValueError("typed payload types must be str")
    return type_name, base64.b64decode(encoded.encode("ascii"))


def _serialize_snapshot(
        storage: Mapping[str, Any],
        writes: Mapping[tuple[Any, ...], Mapping[tuple[Any, ...], Any]],
        blobs: Mapping[tuple[Any, ...], Any],
) -> dict[str, Any]:
    storage_out: dict[str, Any] = {}
    for ns, checkpoints in storage.items():
        ns_out: dict[str, Any] = {}
        for checkpoint_id, entry in checkpoints.items():
            ckpt, meta, parent = entry
            ns_out[str(checkpoint_id)] = {
                "checkpoint": _encode_typed(ckpt),
                "metadata": _encode_typed(meta),
                "parent": parent,
            }
        storage_out[str(ns)] = ns_out

    writes_out: list[dict[str, Any]] = []
    for outer_key, inner in writes.items():
        writes_out.append(
            {
                "key": list(outer_key),
                "entries": [
                    {
                        "key": list(inner_key),
                        "value": [
                            task_id,
                            channel,
                            _encode_typed(typed_value),
                            task_path,
                        ],
                    }
                    for inner_key, (task_id, channel, typed_value, task_path) in inner.items()
                ],
            }
        )

    blobs_out: list[dict[str, Any]] = []
    for key, typed_value in blobs.items():
        blobs_out.append({"key": list(key), "value": _encode_typed(typed_value)})

    return {
        "format": _FORMAT,
        "storage": storage_out,
        "writes": writes_out,
        "blobs": blobs_out,
    }


def _deserialize_snapshot(raw: Mapping[str, Any]) -> tuple[dict[str, Any], dict[Any, Any], dict[Any, Any]]:
    storage_out: dict[str, Any] = {}
    for ns, checkpoints in (raw.get("storage") or {}).items():
        ns_out: dict[str, Any] = {}
        for checkpoint_id, entry in checkpoints.items():
            if not isinstance(entry, Mapping):
                raise ValueError("checkpoint entry must be object")
            ns_out[str(checkpoint_id)] = (
                _decode_typed(entry["checkpoint"]),
                _decode_typed(entry["metadata"]),
                entry.get("parent"),
            )
        storage_out[str(ns)] = ns_out

    writes_out: dict[Any, Any] = {}
    for item in raw.get("writes") or []:
        outer_key = tuple(item["key"])
        inner_map: dict[Any, Any] = {}
        for entry in item.get("entries") or []:
            inner_key_raw = entry["key"]
            inner_key = (str(inner_key_raw[0]), int(inner_key_raw[1]))
            task_id, channel, typed_value, task_path = entry["value"]
            inner_map[inner_key] = (
                str(task_id),
                str(channel),
                _decode_typed(typed_value),
                str(task_path),
            )
        writes_out[outer_key] = inner_map

    blobs_out: dict[Any, Any] = {}
    for item in raw.get("blobs") or []:
        blobs_out[tuple(item["key"])] = _decode_typed(item["value"])

    return storage_out, writes_out, blobs_out


class StoreBackedCheckpointSaver(InMemorySaver):
    def __init__(self, store: RunCheckpointStore, key_prefix: str = "lg:") -> None:
        super().__init__(serde=_checkpoint_serde())
        self._store = store
        self._prefix = key_prefix
        self._hydrated: set[str] = set()
        self._lock = asyncio.Lock()

    def thread_key(self, thread_id: str) -> str:
        return f"{self._prefix}{thread_id}"

    async def _hydrate(self, thread_id: str) -> None:
        if not thread_id:
            return

        key = self.thread_key(thread_id)
        raw = await self._store.load(key)

        if raw is None:
            self._clear_thread_local(thread_id)
            self._hydrated.add(thread_id)
            return

        if not isinstance(raw, dict) or raw.get("format") != _FORMAT:
            _logger.warning(
                "Discarding unsupported or corrupt LangGraph checkpoint key=%s format=%r",
                key,
                raw.get("format") if isinstance(raw, dict) else type(raw).__name__,
            )
            await self._store.delete(key)
            self._clear_thread_local(thread_id)
            self._hydrated.add(thread_id)
            return

        try:
            storage, writes, blobs = _deserialize_snapshot(raw)
        except Exception:
            _logger.exception(
                "Failed to decode LangGraph checkpoint key=%s; discarding",
                key,
            )
            await self._store.delete(key)
            self._clear_thread_local(thread_id)
            self._hydrated.add(thread_id)
            return

        self._clear_thread_local(thread_id)
        ns_map = self.storage[thread_id]
        for ns, checkpoints in storage.items():
            ns_map[str(ns)].update(checkpoints)
        for write_key, value in writes.items():
            self.writes[write_key] = value
        for blob_key, value in blobs.items():
            self.blobs[blob_key] = value

        self._hydrated.add(thread_id)

    def _clear_thread_local(self, thread_id: str) -> None:
        if thread_id in self.storage:
            self.storage[thread_id].clear()
        for write_key in [key for key in self.writes if key[0] == thread_id]:
            del self.writes[write_key]
        for blob_key in [key for key in self.blobs if key[0] == thread_id]:
            del self.blobs[blob_key]

    async def _persist(self, thread_id: str) -> None:
        if not thread_id or thread_id not in self._hydrated:
            return
        writes = {key: value for key, value in self.writes.items() if key[0] == thread_id}
        blobs = {key: value for key, value in self.blobs.items() if key[0] == thread_id}
        payload = _serialize_snapshot(
            storage=dict(self.storage.get(thread_id, {})),
            writes=writes,
            blobs=blobs,
        )
        await self._store.save(self.thread_key(thread_id), payload)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = str(config.get("configurable", {}).get("thread_id") or "")
        async with self._lock:
            await self._hydrate(thread_id)
            return await super().aget_tuple(config)

    async def aput(
            self,
            config: RunnableConfig,
            checkpoint: Checkpoint,
            metadata: CheckpointMetadata,
            new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = str(config.get("configurable", {}).get("thread_id") or "")
        async with self._lock:
            await self._hydrate(thread_id)
            result = await super().aput(config, checkpoint, metadata, new_versions)
            await self._persist(thread_id)
            return result

    async def aput_writes(
            self,
            config: RunnableConfig,
            writes: Sequence[tuple[str, Any]],
            task_id: str,
            task_path: str = "",
    ) -> None:
        thread_id = str(config.get("configurable", {}).get("thread_id") or "")
        async with self._lock:
            await self._hydrate(thread_id)
            await super().aput_writes(config, writes, task_id, task_path)
            await self._persist(thread_id)

    async def adelete_thread(self, thread_id: str) -> None:
        async with self._lock:
            await super().adelete_thread(thread_id)
            self._hydrated.discard(thread_id)
            await self._store.delete(self.thread_key(thread_id))
