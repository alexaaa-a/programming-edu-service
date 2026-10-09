import logging
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from agent_service.app.application.graph_memory import extraction, gates
from agent_service.app.application.graph_memory.facts import (
    EpisodeKind,
    FactOperation,
    GraphFact,
    MemoryEpisode,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import EXHIBITS
from agent_service.app.application.graph_memory.projection import profile_facts
from agent_service.app.application.graph_memory.trust import (
    Resolution,
    cap_confidence,
    may_override,
    resolve,
)
from agent_service.app.application.interfaces.decisions import DecisionModelInterface
from agent_service.app.application.interfaces.graph_memory import GraphMemoryInterface
from agent_service.app.application.interfaces.llm import LLMInterface
from agent_service.app.application.observability.llm_trace import LlmTracer, get_noop_tracer
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


MAX_FACTS_PER_EPISODE = 8


@dataclass(frozen=True, slots=True)
class CurationResult:
    episode_id: str
    user_id: str
    added: int = 0
    reinforced: int = 0
    invalidated: int = 0
    skipped: int = 0
    model_facts: int = 0
    profile: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)

    @property
    def written(self) -> int:
        return self.added + self.reinforced + self.invalidated


class MemoryCurator:
    def __init__(
            self,
            graph: GraphMemoryInterface,
            llm: LLMInterface | None = None,
            decisions: DecisionModelInterface | None = None,
            logger: logging.Logger | None = None,
            metrics: MetricsRecorder | None = None,
            tracer: LlmTracer | None = None,
            min_confidence: float = 0.6,
            model_extraction_enabled: bool = True,
    ) -> None:
        self._graph = graph
        self._llm = llm
        self._decisions = decisions
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()
        self._min_confidence = min_confidence
        self._model_extraction_enabled = model_extraction_enabled

    @property
    def _decisions_on(self) -> bool:
        return self._decisions is not None and self._decisions.enabled

    async def curate(self, episode: MemoryEpisode) -> CurationResult:
        if not self._graph.enabled or not episode.user_id:
            return CurationResult(episode.episode_id, episode.user_id)

        existing = await self._graph.all_facts(episode.user_id)
        by_key: dict[str, list[StoredFact]] = {}
        for item in existing:
            by_key.setdefault(item.key, []).append(item)

        candidates = extraction.observations_to_facts(episode)
        candidates.extend(
            extraction.fixed_pattern_facts(
                episode,
                [item for item in existing if item.relation == EXHIBITS],
            )
        )
        model_facts = await self._ask_model(episode, existing)
        candidates.extend(model_facts)
        candidates = _dedupe(candidates)[:MAX_FACTS_PER_EPISODE]
        if not candidates:
            return CurationResult(episode.episode_id, episode.user_id, model_facts=len(model_facts))

        candidates = [cap_confidence(fact) for fact in candidates]
        resolutions = [resolve(fact, by_key.get(fact.key, []) + _opposites(fact, by_key)) for fact in candidates]
        decisions = await self._ask_decisions(episode, candidates, by_key, resolutions)

        result = await self._apply(episode, candidates, resolutions, decisions)
        projection = await self._refresh_projection(episode, written=result.written)
        return replace(result, model_facts=len(model_facts), profile=projection)

    async def _ask_model(
            self,
            episode: MemoryEpisode,
            existing: Sequence[StoredFact],
    ) -> list[GraphFact]:
        if not self._model_extraction_enabled or self._llm is None or not episode.body.strip():
            return []
        known = sorted({item.target.key for item in existing if item.target.kind == "error_pattern"})
        prompt = extraction.extraction_prompt(episode, known_patterns=known)
        try:
            with self._tracer.observation(
                "graph_memory.extract",
                as_type="generation",
                input={"episode": episode.episode_id, "kind": episode.kind.value},
            ) as obs:
                raw = await self._llm.generate(extraction.EXTRACTION_SYSTEM, prompt)
                facts = extraction.parse_extraction(raw, episode)
                obs.update(output={"facts": len(facts)})
        except Exception:
            self._logger.exception("graph_memory.extract_failed episode=%s", episode.episode_id)
            self._count("graph_memory_extract_failed")
            return []
        return facts

    async def _ask_decisions(
            self,
            episode: MemoryEpisode,
            facts: Sequence[GraphFact],
            by_key: Mapping[str, list[StoredFact]],
            resolutions: Sequence[Resolution],
    ) -> list[gates.GateDecision]:
        fallback = [
            gates.GateDecision(
                _rule_operation(fact, resolution),
                source="rules",
                reason=resolution.reason,
            )
            for fact, resolution in zip(facts, resolutions)
        ]
        if not self._decisions_on or self._decisions is None:
            return fallback
        try:
            answers = await self._decisions.ask(
                gates.gate_state(facts, by_key, episode.body),
                gates.gate_questions(facts),
                label="memory_curation",
            )
        except Exception:
            self._logger.exception("graph_memory.gate_failed episode=%s", episode.episode_id)
            return fallback
        if not answers:
            return fallback
        return [
            gates.read_gate(answers, index, fallback[index].operation, self._min_confidence)
            for index in range(len(facts))
        ]

    async def _apply(
            self,
            episode: MemoryEpisode,
            facts: Sequence[GraphFact],
            resolutions: Sequence[Resolution],
            decisions: Sequence[gates.GateDecision],
    ) -> CurationResult:
        added = reinforced = invalidated = skipped = 0
        trail: list[str] = []

        for fact, resolution, decision in zip(facts, resolutions, decisions):
            operation = self._guard(fact, resolution, decision)
            trail.append(f"{fact.key}={operation.value}:{decision.source}")
            if operation is FactOperation.SKIP:
                skipped += 1
                continue
            if operation is FactOperation.INVALIDATE:
                closed = await self._close_same(fact, resolution)
                invalidated += closed
                if closed == 0:
                    skipped += 1
                continue
            for stale in resolution.invalidate:
                if await self._graph.invalidate(stale, fact.occurred_at, reason="contradicted"):
                    invalidated += 1
            written = await self._graph.write(fact.with_operation(operation))
            if written.operation is FactOperation.REINFORCE:
                reinforced += 1
            elif written.written:
                added += 1
            else:
                skipped += 1

        self._count("graph_memory_facts_added", added)
        self._count("graph_memory_facts_reinforced", reinforced)
        self._count("graph_memory_facts_invalidated", invalidated)
        self._count("graph_memory_facts_skipped", skipped)

        return CurationResult(
            episode_id=episode.episode_id,
            user_id=episode.user_id,
            added=added,
            reinforced=reinforced,
            invalidated=invalidated,
            skipped=skipped,
            decisions=trail,
        )

    def _guard(
            self,
            fact: GraphFact,
            resolution: Resolution,
            decision: gates.GateDecision,
    ) -> FactOperation:
        operation = decision.operation
        if operation is FactOperation.SKIP:
            return operation

        if operation is FactOperation.INVALIDATE:
            targets = _closable(resolution)
            if not self._may_close(fact, targets):
                self._count("graph_memory_guard_blocked")
                return FactOperation.SKIP
            return operation

        if resolution.operation is FactOperation.SKIP and decision.from_model:
            if resolution.reason in {"weaker_than_existing", "older_than_existing"}:
                self._count("graph_memory_guard_blocked")
                return FactOperation.SKIP

        if resolution.invalidate and not self._may_close(fact, resolution.invalidate):
            return FactOperation.SKIP

        return operation

    def _may_close(self, fact: GraphFact, targets: Sequence[StoredFact]) -> bool:
        if not targets:
            return False
        return all(may_override(fact.source, item.source) for item in targets)

    async def _close_same(self, fact: GraphFact, resolution: Resolution) -> int:
        targets = _closable(resolution)
        closed = 0
        for item in targets:
            if await self._graph.invalidate(item, fact.occurred_at, reason="resolved"):
                closed += 1
        return closed

    async def _refresh_projection(self, episode: MemoryEpisode, written: int) -> list[str]:
        if episode.mastery:
            try:
                await self._graph.remember_mastery(episode.user_id, episode.mastery)
            except Exception:
                self._logger.exception("graph_memory.mastery_failed user=%s", episode.user_id)
        if written == 0:
            return []
        try:
            facts = await self._graph.all_facts(episode.user_id)
        except Exception:
            self._logger.exception("graph_memory.projection_failed user=%s", episode.user_id)
            return []
        return profile_facts(facts)

    def _count(self, name: str, value: int = 1) -> None:
        if self._metrics is None or value <= 0:
            return
        try:
            self._metrics.increment(name, value)
        except Exception:
            self._logger.debug("graph_memory metric failed: %s", name)


def _rule_operation(fact: GraphFact, resolution: Resolution) -> FactOperation:
    if fact.operation is FactOperation.INVALIDATE:
        return FactOperation.INVALIDATE
    if resolution.operation is FactOperation.SKIP:
        return FactOperation.SKIP
    if not gates.heuristic_keep(fact):
        return FactOperation.SKIP
    return resolution.operation


def _closable(resolution: Resolution) -> tuple[StoredFact, ...]:
    return resolution.same or resolution.invalidate


def _opposites(fact: GraphFact, by_key: Mapping[str, list[StoredFact]]) -> list[StoredFact]:
    out: list[StoredFact] = []
    for key, items in by_key.items():
        if key == fact.key:
            continue
        out.extend(item for item in items if item.target.key == fact.target.key)
    return out


def _dedupe(facts: Sequence[GraphFact]) -> list[GraphFact]:
    best: dict[str, GraphFact] = {}
    for fact in facts:
        held = best.get(fact.key)
        if held is None or _strength(fact) > _strength(held):
            best[fact.key] = fact
    return list(best.values())


def _strength(fact: GraphFact) -> tuple[int, float]:
    rank = {SourceKind.HIDDEN_TESTS: 3, SourceKind.REVIEW: 2, SourceKind.TRAJECTORY: 2}.get(fact.source, 1)
    return (rank, fact.confidence)


def episode_body_for_chat(message: str, speaker: str, answer: str) -> str:
    return f"Student: {message.strip()}\n{speaker}: {answer.strip()}"


def episode_kind_of(value: str) -> EpisodeKind:
    return EpisodeKind(value) if value in {item.value for item in EpisodeKind} else EpisodeKind.REVIEW
