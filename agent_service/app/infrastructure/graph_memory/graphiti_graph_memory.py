import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

from graphiti_core.edges import EntityEdge

from agent_service.app.application.graph_memory.facts import (
    FactOperation,
    FactTarget,
    GraphFact,
    GraphWriteResult,
    SourceKind,
    StoredFact,
    utc_now,
)
from agent_service.app.application.graph_memory.extraction import pattern_skill
from agent_service.app.application.graph_memory.ontology import (
    EXHIBITS,
    INSTANCE_OF,
    SKILL,
    SKILL_BY_ID,
    STUDENT,
    group_id_for,
    node_uuid,
    user_id_of_group,
)
from agent_service.app.application.graph_memory.recipes import (
    ReadIntent,
    Reranker,
    recipe_for,
)
from agent_service.app.application.interfaces.graph_memory import GraphMemoryInterface
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


_STUDENT_KEY = "self"


class GraphitiGraphMemory(GraphMemoryInterface):
    def __init__(
            self,
            client: Any,
            logger: logging.Logger | None = None,
            metrics: MetricsRecorder | None = None,
            timeout_sec: float = 8.0,
            write_timeout_sec: float = 25.0,
    ) -> None:
        self._client = client
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = metrics
        self._timeout = timeout_sec
        self._write_timeout = write_timeout_sec
        self._schema_ready = False

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def ensure_schema(self) -> None:
        if not self.enabled or self._schema_ready:
            return
        try:
            await asyncio.wait_for(
                self._client.build_indices_and_constraints(),
                timeout=max(self._write_timeout, 60.0),
            )
            self._schema_ready = True
            self._logger.info("graph_memory.schema_ready")
        except Exception:
            self._logger.exception("graph_memory.schema_failed")

    async def write(self, fact: GraphFact) -> GraphWriteResult:
        if not self.enabled:
            return GraphWriteResult(FactOperation.SKIP)
        try:
            if fact.operation is FactOperation.REINFORCE:
                return await self._reinforce(fact)
            return await self._add(fact)
        except asyncio.TimeoutError:
            self._count("graph_memory_write_timeout")
            self._logger.warning("graph_memory.write_timeout key=%s", fact.key)
        except Exception:
            self._count("graph_memory_write_failed")
            self._logger.exception("graph_memory.write_failed key=%s", fact.key)
        return GraphWriteResult(FactOperation.SKIP)

    async def _add(self, fact: GraphFact) -> GraphWriteResult:
        from graphiti_core.edges import EntityEdge

        group = group_id_for(fact.user_id)
        source_node = self._student_node(group, fact.user_id)
        target_node = self._target_node(group, fact.target)
        edge = EntityEdge(
            uuid=str(uuid4()),
            group_id=group,
            source_node_uuid=source_node.uuid,
            target_node_uuid=target_node.uuid,
            name=fact.relation,
            fact=fact.statement,
            created_at=utc_now(),
            valid_at=fact.occurred_at,
            attributes=self._edge_attributes(fact),
        )
        result = await asyncio.wait_for(
            self._client.add_triplet(source_node, edge, target_node),
            timeout=self._write_timeout,
        )
        invalidated = sum(
            1 for item in getattr(result, "edges", []) if getattr(item, "invalid_at", None) is not None
        )
        await self._anchor_pattern(group, fact)
        self._count("graph_memory_write_ok")
        return GraphWriteResult(FactOperation.ADD, edge_uuid=edge.uuid, invalidated=invalidated)

    async def _reinforce(self, fact: GraphFact) -> GraphWriteResult:
        existing = await self._valid_edges_for(fact.user_id, fact.relation, fact.target)
        if not existing:
            return await self._add(fact)
        edge = existing[0]
        attributes = dict(edge.attributes or {})
        occurrences = int(attributes.get("occurrences") or 1) + 1
        attributes["occurrences"] = occurrences
        attributes["last_seen_at"] = fact.occurred_at.isoformat()
        attributes["confidence"] = round(
            min(0.98, max(float(attributes.get("confidence") or 0.5), fact.confidence) + 0.05),
            3,
        )
        if fact.submission_id:
            attributes["submission_id"] = str(fact.submission_id)
        attributes["source_kind"] = _stronger_source(
            str(attributes.get("source_kind") or ""), fact.source
        )
        edge.attributes = attributes
        await asyncio.wait_for(edge.save(self._client.driver), timeout=self._write_timeout)
        self._count("graph_memory_write_ok")
        return GraphWriteResult(FactOperation.REINFORCE, edge_uuid=edge.uuid)

    async def invalidate(self, fact: StoredFact, at: datetime, reason: str = "") -> bool:
        if not self.enabled:
            return False
        try:
            from graphiti_core.edges import EntityEdge

            edge = await asyncio.wait_for(
                EntityEdge.get_by_uuid(self._client.driver, fact.edge_uuid),
                timeout=self._timeout,
            )
            if getattr(edge, "invalid_at", None) is not None:
                return False
            edge.invalid_at = at
            attributes = dict(edge.attributes or {})
            attributes["invalidation_reason"] = reason or "contradicted"
            edge.attributes = attributes
            await asyncio.wait_for(edge.save(self._client.driver), timeout=self._write_timeout)
            self._count("graph_memory_invalidated")
            return True
        except Exception:
            self._logger.exception("graph_memory.invalidate_failed edge=%s", fact.edge_uuid)
            return False

    async def update_confidence(
            self,
            fact: StoredFact,
            confidence: float,
            chronic: bool = False,
    ) -> bool:
        if not self.enabled:
            return False
        try:
            from graphiti_core.edges import EntityEdge

            edge = await asyncio.wait_for(
                EntityEdge.get_by_uuid(self._client.driver, fact.edge_uuid),
                timeout=self._timeout,
            )
            attributes = dict(edge.attributes or {})
            attributes["confidence"] = round(max(0.0, min(1.0, float(confidence))), 3)
            attributes["chronic"] = bool(chronic)
            edge.attributes = attributes
            await asyncio.wait_for(edge.save(self._client.driver), timeout=self._write_timeout)
            return True
        except Exception:
            self._logger.exception("graph_memory.update_failed edge=%s", fact.edge_uuid)
            return False

    async def merge_facts(self, keep: StoredFact, drop: StoredFact, occurrences: int) -> bool:
        if not self.enabled:
            return False
        try:
            survivor = await asyncio.wait_for(
                EntityEdge.get_by_uuid(self._client.driver, keep.edge_uuid),
                timeout=self._timeout,
            )
            attributes = dict(survivor.attributes or {})
            attributes["occurrences"] = int(occurrences)
            merged = list(attributes.get("merged_from") or [])
            merged.append(drop.target.key)
            attributes["merged_from"] = merged[:10]
            survivor.attributes = attributes
            await asyncio.wait_for(survivor.save(self._client.driver), timeout=self._write_timeout)
        except Exception:
            self._logger.exception("graph_memory.merge_failed edge=%s", keep.edge_uuid)
            return False
        return await self.invalidate(drop, utc_now(), reason="merged_duplicate")

    async def facts_for(
            self,
            user_id: str,
            intent: ReadIntent,
            query: str = "",
            skill_ids: Sequence[str] = (),
            limit: int | None = None,
    ) -> list[StoredFact]:
        if not self.enabled or not user_id:
            return []
        recipe = recipe_for(intent)
        take = int(limit or recipe.limit)
        text = (query or "").strip() or recipe.summary
        try:
            group = group_id_for(user_id)
        except ValueError:
            return []
        try:
            config, center = self._search_config(recipe, group, skill_ids)
            results = await asyncio.wait_for(
                self._client.search_(
                    query=text,
                    config=config,
                    group_ids=[group],
                    center_node_uuid=center,
                    search_filter=self._search_filter(recipe),
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            self._count("graph_memory_read_timeout")
            self._logger.warning("graph_memory.read_timeout intent=%s", intent.value)
            return []
        except Exception:
            self._count("graph_memory_read_failed")
            self._logger.exception("graph_memory.read_failed intent=%s", intent.value)
            return []

        facts = [
            fact
            for fact in (_as_stored_fact(edge) for edge in getattr(results, "edges", []))
            if fact is not None
        ]
        if recipe.relations:
            facts = [fact for fact in facts if fact.relation in recipe.relations]
        if not recipe.include_closed:
            facts = [fact for fact in facts if fact.is_valid]
        self._count("graph_memory_read_ok")
        return facts[:take]

    async def all_facts(self, user_id: str, include_closed: bool = False) -> list[StoredFact]:
        if not self.enabled or not user_id:
            return []
        try:
            from graphiti_core.edges import EntityEdge

            group = group_id_for(user_id)
            edges = await asyncio.wait_for(
                EntityEdge.get_by_group_ids(self._client.driver, [group], limit=500),
                timeout=self._timeout,
            )
        except Exception as error:
            if _is_not_found(error):
                return []
            self._logger.exception("graph_memory.all_facts_failed user=%s", user_id)
            return []
        facts = [fact for fact in (_as_stored_fact(edge) for edge in edges) if fact is not None]
        if include_closed:
            return facts
        return [fact for fact in facts if fact.is_valid]

    async def known_pattern_slugs(self, user_id: str) -> list[str]:
        facts = await self.all_facts(user_id, include_closed=True)
        return sorted({fact.target.key for fact in facts if fact.target.kind == "error_pattern"})

    async def remember_mastery(self, user_id: str, mastery: dict[str, float]) -> None:
        if not self.enabled or not mastery:
            return
        clean = {
            str(key): round(float(value), 4)
            for key, value in mastery.items()
            if str(key) in SKILL_BY_ID and isinstance(value, (int, float))
        }
        if not clean:
            return
        try:
            group = group_id_for(user_id)
            node = self._student_node(group, user_id)
            node.attributes = {
                **(node.attributes or {}),
                "mastery": clean,
                "mastery_at": utc_now().isoformat(),
            }
            await node.generate_name_embedding(self._client.embedder)
            await asyncio.wait_for(node.save(self._client.driver), timeout=self._write_timeout)
        except Exception:
            self._logger.exception("graph_memory.mastery_save_failed user=%s", user_id)

    async def mastery_of(self, user_id: str) -> dict[str, float]:
        if not self.enabled:
            return {}
        try:
            from graphiti_core.nodes import EntityNode

            group = group_id_for(user_id)
            node = await asyncio.wait_for(
                EntityNode.get_by_uuid(
                    self._client.driver,
                    node_uuid(group, STUDENT, _STUDENT_KEY),
                ),
                timeout=self._timeout,
            )
        except Exception:
            return {}
        raw = (node.attributes or {}).get("mastery")
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): float(value)
            for key, value in raw.items()
            if str(key) in SKILL_BY_ID and isinstance(value, (int, float))
        }

    async def students_with_memory(self, limit: int = 200) -> list[str]:
        if not self.enabled:
            return []
        try:
            records, _, _ = await asyncio.wait_for(
                self._client.driver.execute_query(
                    """
                    MATCH (n:Entity)
                    WHERE n.group_id STARTS WITH $prefix
                    RETURN DISTINCT n.group_id AS group_id
                    LIMIT $limit
                    """,
                    prefix="student_",
                    limit=int(limit),
                ),
                timeout=self._timeout,
            )
        except Exception:
            self._logger.exception("graph_memory.students_failed")
            return []
        out: list[str] = []
        for record in records or []:
            group = _record_value(record, "group_id")
            if group:
                out.append(user_id_of_group(str(group)))
        return out

    async def forget_student(self, user_id: str) -> int:
        if not self.enabled:
            return 0
        try:
            group = group_id_for(user_id)
        except ValueError:
            return 0
        try:
            records, _, _ = await asyncio.wait_for(
                self._client.driver.execute_query(
                    """
                    MATCH (n {group_id: $group})
                    DETACH DELETE n
                    RETURN count(n) AS removed
                    """,
                    group=group,
                ),
                timeout=max(self._write_timeout, 30.0),
            )
        except Exception:
            self._logger.exception("graph_memory.forget_failed user=%s", user_id)
            return 0
        removed = 0
        for record in records or []:
            value = _record_value(record, "removed")
            if isinstance(value, int):
                removed = value
        self._logger.info("graph_memory.forgotten user=%s nodes=%s", user_id, removed)
        self._count("graph_memory_forgotten")
        return removed

    def _student_node(self, group: str, user_id: str) -> Any:
        from graphiti_core.nodes import EntityNode

        return EntityNode(
            uuid=node_uuid(group, STUDENT, _STUDENT_KEY),
            name=f"student {user_id}",
            group_id=group,
            labels=["Entity", STUDENT],
            summary="The learner this subgraph belongs to.",
            attributes={"user_id": str(user_id)},
        )

    def _target_node(self, group: str, target: FactTarget) -> Any:
        from graphiti_core.nodes import EntityNode

        label = target.label
        if not label:
            raise ValueError(f"unknown target kind: {target.kind}")
        summary = ""
        if target.kind == "skill":
            skill = SKILL_BY_ID.get(target.key)
            summary = skill.summary if skill else ""
        elif target.kind == "error_pattern":
            summary = target.name
        return EntityNode(
            uuid=node_uuid(group, label, target.key),
            name=target.display_name(),
            group_id=group,
            labels=["Entity", label],
            summary=summary,
            attributes={"key": target.key, "kind": target.kind},
        )

    async def _anchor_pattern(self, group: str, fact: GraphFact) -> None:
        if fact.relation != EXHIBITS:
            return
        skill_id = pattern_skill(fact.target)
        if skill_id is None:
            return
        try:
            from graphiti_core.edges import EntityEdge

            skill = SKILL_BY_ID[skill_id]
            pattern_node = self._target_node(group, fact.target)
            skill_node = self._target_node(group, FactTarget("skill", skill.id, skill.name))
            edge = EntityEdge(
                uuid=node_uuid(group, INSTANCE_OF, f"{fact.target.key}->{skill.id}"),
                group_id=group,
                source_node_uuid=pattern_node.uuid,
                target_node_uuid=skill_node.uuid,
                name=INSTANCE_OF,
                fact=f"The mistake '{fact.target.key}' belongs to {skill.name.lower()}.",
                created_at=utc_now(),
                valid_at=fact.occurred_at,
                attributes={
                    "relation": INSTANCE_OF,
                    "target_kind": "skill",
                    "target_key": skill.id,
                    "target_name": skill.name,
                    "source_kind": SourceKind.REVIEW.value,
                    "confidence": 1.0,
                    "occurrences": 1,
                },
            )
            await asyncio.wait_for(
                self._client.add_triplet(pattern_node, edge, skill_node),
                timeout=self._write_timeout,
            )
        except Exception:
            self._logger.debug("graph_memory.anchor_failed pattern=%s", fact.target.key)

    async def _valid_edges_for(
            self,
            user_id: str,
            relation: str,
            target: FactTarget,
    ) -> list[Any]:
        from graphiti_core.edges import EntityEdge

        group = group_id_for(user_id)
        try:
            edges = await asyncio.wait_for(
                EntityEdge.get_between_nodes(
                    self._client.driver,
                    node_uuid(group, STUDENT, _STUDENT_KEY),
                    node_uuid(group, target.label, target.key),
                ),
                timeout=self._timeout,
            )
        except Exception as error:
            if not _is_not_found(error):
                self._logger.debug("graph_memory.lookup_failed relation=%s", relation)
            return []
        return [
            edge
            for edge in edges
            if edge.name == relation and getattr(edge, "invalid_at", None) is None
        ]

    def _search_config(
            self,
            recipe: Any,
            group: str,
            skill_ids: Sequence[str],
    ) -> tuple[Any, str | None]:
        from graphiti_core.search.search_config_recipes import (
            EDGE_HYBRID_SEARCH_EPISODE_MENTIONS,
            EDGE_HYBRID_SEARCH_NODE_DISTANCE,
            EDGE_HYBRID_SEARCH_RRF,
        )

        center: str | None = None
        if recipe.center_on_skill:
            anchor = next((item for item in skill_ids if item in SKILL_BY_ID), "")
            if anchor:
                center = node_uuid(group, SKILL, anchor)

        if recipe.reranker is Reranker.NODE_DISTANCE and center:
            config = EDGE_HYBRID_SEARCH_NODE_DISTANCE.model_copy(deep=True)
        elif recipe.reranker is Reranker.EPISODE_MENTIONS:
            config = EDGE_HYBRID_SEARCH_EPISODE_MENTIONS.model_copy(deep=True)
        else:
            config = EDGE_HYBRID_SEARCH_RRF.model_copy(deep=True)
            center = None
        config.limit = int(recipe.limit)
        return config, center

    def _search_filter(self, recipe: Any) -> Any:
        from graphiti_core.search.search_filters import (
            ComparisonOperator,
            DateFilter,
            SearchFilters,
        )

        edge_types = list(recipe.relations) or None
        if recipe.include_closed:
            return SearchFilters(edge_types=edge_types)
        return SearchFilters(
            edge_types=edge_types,
            invalid_at=[[DateFilter(date=None, comparison_operator=ComparisonOperator.is_null)]],
        )

    def _edge_attributes(self, fact: GraphFact) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "relation": fact.relation,
            "target_kind": fact.target.kind,
            "target_key": fact.target.key,
            "target_name": fact.target.display_name(),
            "occurrences": 1,
            "chronic": False,
            "last_seen_at": fact.occurred_at.isoformat(),
        }
        attributes.update(fact.evidence())
        return attributes

    def _count(self, name: str, value: int = 1) -> None:
        if self._metrics is None or value <= 0:
            return
        try:
            self._metrics.increment(name, value)
        except Exception:
            self._logger.debug("graph_memory metric failed: %s", name)


def _as_stored_fact(edge: Any) -> StoredFact | None:
    attributes = getattr(edge, "attributes", None) or {}
    target_kind = str(attributes.get("target_kind") or "")
    target_key = str(attributes.get("target_key") or "")
    relation = str(getattr(edge, "name", "") or attributes.get("relation") or "")
    if not target_kind or not target_key or not relation or relation == INSTANCE_OF:
        return None
    created = _as_datetime(getattr(edge, "created_at", None)) or utc_now()
    occurred = _as_datetime(getattr(edge, "valid_at", None)) or created
    return StoredFact(
        edge_uuid=str(getattr(edge, "uuid", "")),
        user_id=user_id_of_group(str(getattr(edge, "group_id", ""))),
        relation=relation,
        target=FactTarget(
            kind=target_kind,
            key=target_key,
            name=str(attributes.get("target_name") or ""),
        ),
        statement=str(getattr(edge, "fact", "") or ""),
        source=_as_source(attributes.get("source_kind")),
        confidence=_as_float(attributes.get("confidence"), 0.5),
        occurred_at=occurred,
        created_at=created,
        valid_until=_as_datetime(getattr(edge, "invalid_at", None)),
        occurrences=max(1, int(_as_float(attributes.get("occurrences"), 1.0))),
        last_seen_at=_as_datetime(attributes.get("last_seen_at")) or occurred,
        task_id=_as_optional_str(attributes.get("task_id")),
        submission_id=_as_optional_str(attributes.get("submission_id")),
    )


def _stronger_source(existing: str, incoming: SourceKind) -> str:
    rank = {
        SourceKind.HIDDEN_TESTS.value: 3,
        SourceKind.REVIEW.value: 2,
        SourceKind.TRAJECTORY.value: 2,
        SourceKind.CHAT.value: 1,
    }
    if rank.get(incoming.value, 1) >= rank.get(existing, 0):
        return incoming.value
    return existing


def _as_source(raw: Any) -> SourceKind:
    text = str(raw or "")
    for item in SourceKind:
        if item.value == text:
            return item
    return SourceKind.REVIEW


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        try:
            native = to_native()
        except Exception:
            return None
        if isinstance(native, datetime):
            return native if native.tzinfo else native.replace(tzinfo=timezone.utc)
    return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    getter = getattr(record, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    try:
        return record[key]
    except Exception:
        return None


def _is_not_found(error: Exception) -> bool:
    return type(error).__name__ in {"NodeNotFoundError", "EdgeNotFoundError", "GroupsEdgesNotFoundError"}
