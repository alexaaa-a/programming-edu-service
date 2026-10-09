import asyncio
import logging
from typing import Awaitable, Callable

from agent_service.app.application.graph_memory.consolidation import (
    ConsolidationReport,
    plan_consolidation,
)
from agent_service.app.application.graph_memory.curator import MemoryCurator
from agent_service.app.application.graph_memory.facts import utc_now
from agent_service.app.application.graph_memory.projection import profile_facts
from agent_service.app.application.interfaces.graph_memory import GraphMemoryInterface
from agent_service.app.application.interfaces.memory_episode_queue import MemoryEpisodeQueue
from agent_service.app.application.interfaces.student_profile import StudentProfileRepository
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder


class MemoryIngestWorker:
    def __init__(
            self,
            queue: MemoryEpisodeQueue,
            curator: MemoryCurator,
            graph: GraphMemoryInterface,
            profiles: StudentProfileRepository | None = None,
            logger: logging.Logger | None = None,
            metrics: MetricsRecorder | None = None,
            batch_size: int = 4,
            idle_sleep_sec: float = 5.0,
            busy_sleep_sec: float = 0.5,
    ) -> None:
        self._queue = queue
        self._curator = curator
        self._graph = graph
        self._profiles = profiles
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = metrics
        self._batch_size = batch_size
        self._idle_sleep = idle_sleep_sec
        self._busy_sleep = busy_sleep_sec

    async def run(self) -> None:
        if not self._graph.enabled:
            self._logger.info("graph_memory.ingest_worker_skipped reason=disabled")
            return
        self._logger.info("graph_memory.ingest_worker_started")
        while True:
            try:
                handled = await self.run_once()
            except asyncio.CancelledError:
                self._logger.info("graph_memory.ingest_worker_stopped")
                raise
            except Exception:
                self._logger.exception("graph_memory.ingest_loop_failed")
                handled = 0
            await asyncio.sleep(self._busy_sleep if handled else self._idle_sleep)

    async def run_once(self) -> int:
        episodes = await self._queue.claim(self._batch_size)
        for episode in episodes:
            try:
                result = await self._curator.curate(episode)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._logger.exception("graph_memory.curate_failed episode=%s", episode.episode_id)
                await self._queue.mark_failed(episode.episode_id, f"{type(error).__name__}: {error}")
                continue
            await self._queue.mark_done(episode.episode_id, facts_written=result.written)
            await self._save_projection(episode.user_id, result.profile)
            self._logger.info(
                "graph_memory.curated episode=%s user=%s added=%s reinforced=%s "
                "invalidated=%s skipped=%s decisions=%s",
                episode.episode_id,
                episode.user_id,
                result.added,
                result.reinforced,
                result.invalidated,
                result.skipped,
                ",".join(result.decisions[:6]),
            )
        return len(episodes)

    async def _save_projection(self, user_id: str, facts: list[str]) -> None:
        if not facts or self._profiles is None or not user_id:
            return
        try:
            await self._profiles.save(user_id, facts)
        except Exception:
            self._logger.exception("graph_memory.projection_save_failed user=%s", user_id)


class MemoryConsolidationWorker:
    def __init__(
            self,
            graph: GraphMemoryInterface,
            profiles: StudentProfileRepository | None = None,
            logger: logging.Logger | None = None,
            metrics: MetricsRecorder | None = None,
            interval_sec: float = 21_600.0,
            first_delay_sec: float = 300.0,
            max_students: int = 200,
            clock: Callable[[], object] | None = None,
    ) -> None:
        self._graph = graph
        self._profiles = profiles
        self._logger = logger or logging.getLogger(__name__)
        self._metrics = metrics
        self._interval = interval_sec
        self._first_delay = first_delay_sec
        self._max_students = max_students
        self._clock = clock or utc_now

    async def run(self) -> None:
        if not self._graph.enabled:
            self._logger.info("graph_memory.consolidation_skipped reason=disabled")
            return
        await asyncio.sleep(self._first_delay)
        self._logger.info("graph_memory.consolidation_started")
        while True:
            try:
                report = await self.run_once()
                self._logger.info(
                    "graph_memory.consolidated students=%s invalidated=%s updated=%s "
                    "merged=%s pruned=%s failed=%s",
                    report.students,
                    report.invalidated,
                    report.updated,
                    report.merged,
                    report.pruned,
                    report.failed,
                )
            except asyncio.CancelledError:
                self._logger.info("graph_memory.consolidation_stopped")
                raise
            except Exception:
                self._logger.exception("graph_memory.consolidation_failed")
            await asyncio.sleep(self._interval)

    async def run_once(self) -> ConsolidationReport:
        report = ConsolidationReport()
        students = await self._graph.students_with_memory(limit=self._max_students)
        for user_id in students:
            try:
                report = report.plus(await self._consolidate_student(user_id))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._logger.exception("graph_memory.consolidate_failed user=%s", user_id)
                report = report.with_failure(f"{user_id}: {type(error).__name__}: {error}")
        self._count("graph_memory_consolidation_invalidated", report.invalidated)
        self._count("graph_memory_consolidation_merged", report.merged)
        return report

    async def _consolidate_student(self, user_id: str):
        facts = await self._graph.all_facts(user_id)
        if not facts:
            from agent_service.app.application.graph_memory.consolidation import ConsolidationPlan

            return ConsolidationPlan()
        mastery = await self._graph.mastery_of(user_id)
        plan = plan_consolidation(facts, mastery=mastery, now=self._clock())
        if plan.is_empty:
            return plan

        for merge in plan.merge:
            await self._graph.merge_facts(merge.keep, merge.drop, merge.occurrences)
        for update in plan.update:
            await self._graph.update_confidence(update.fact, update.confidence, update.chronic)
        for invalidation in plan.invalidate:
            await self._graph.invalidate(
                invalidation.fact,
                self._clock(),
                reason=invalidation.reason,
            )
        for stale in plan.prune:
            await self._graph.invalidate(stale, self._clock(), reason="pruned")

        await self._refresh_projection(user_id)
        return plan

    async def _refresh_projection(self, user_id: str) -> None:
        if self._profiles is None:
            return
        try:
            facts = await self._graph.all_facts(user_id)
            projected = profile_facts(facts)
            if projected:
                await self._profiles.save(user_id, projected)
        except Exception:
            self._logger.exception("graph_memory.projection_refresh_failed user=%s", user_id)

    def _count(self, name: str, value: int) -> None:
        if self._metrics is None or value <= 0:
            return
        try:
            self._metrics.increment(name, value)
        except Exception:
            self._logger.debug("graph_memory metric failed: %s", name)


async def run_forever(task: Callable[[], Awaitable[None]], logger: logging.Logger, name: str) -> None:
    try:
        await task()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("graph_memory.%s_crashed", name)
