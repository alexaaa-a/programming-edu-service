import logging

from dishka import Provider, Scope, provide
from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI

from agent_service.app.application.graph_memory.curator import MemoryCurator
from agent_service.app.application.interfaces import (
    DecisionModelInterface,
    GraphMemoryInterface,
    LLMInterface,
    MemoryEpisodeQueue,
    StudentProfileRepository,
)
from agent_service.app.application.observability.llm_trace import LlmTracer
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.config import Settings
from agent_service.app.infrastructure.graph_memory import (
    GraphitiGraphMemory,
    MemoryConsolidationWorker,
    MemoryIngestWorker,
    NullGraphMemory,
    build_graphiti,
    create_episode_queue,
)
from agent_service.app.setup.ioc.providers.memory import embedding_client_for


class GraphMemoryProvider(Provider):
    @provide(scope=Scope.APP, provides=GraphMemoryInterface)
    def graph_memory(
            self,
            openai_client: AsyncOpenAI,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
    ) -> GraphMemoryInterface:
        client = build_graphiti(
            neo4j=settings.neo4j_settings,
            graph_memory=settings.graph_memory_settings,
            openai_settings=settings.openai_settings,
            llm_client=openai_client,
            embedding_client=embedding_client_for(openai_client, settings),
            logger=logger,
        )
        if client is None:
            return NullGraphMemory()
        return GraphitiGraphMemory(
            client=client,
            logger=logger,
            metrics=metrics_recorder,
            timeout_sec=settings.graph_memory_settings.read_timeout_sec,
            write_timeout_sec=settings.graph_memory_settings.write_timeout_sec,
        )


class MemoryEpisodeQueueProvider(Provider):
    @provide(scope=Scope.APP, provides=MemoryEpisodeQueue)
    async def episode_queue(
            self,
            mongo_client: AsyncIOMotorClient,
            settings: Settings,
            logger: logging.Logger,
    ) -> MemoryEpisodeQueue:
        collection = mongo_client[settings.mongo_settings.name]["memory_episodes"]
        return await create_episode_queue(
            collection,
            logger=logger,
            lease_sec=settings.graph_memory_settings.queue_lease_sec,
            max_attempts=settings.graph_memory_settings.queue_max_attempts,
        )


class MemoryCuratorProvider(Provider):
    @provide(scope=Scope.APP)
    def curator(
            self,
            graph: GraphMemoryInterface,
            llm: LLMInterface,
            decisions: DecisionModelInterface,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
            tracer: LlmTracer,
    ) -> MemoryCurator:
        return MemoryCurator(
            graph=graph,
            llm=llm,
            decisions=decisions,
            logger=logger,
            metrics=metrics_recorder,
            tracer=tracer,
            min_confidence=settings.jev_settings.min_confidence,
            model_extraction_enabled=settings.graph_memory_settings.model_extraction_enabled,
        )


class GraphMemoryWorkersProvider(Provider):
    @provide(scope=Scope.APP)
    def ingest_worker(
            self,
            queue: MemoryEpisodeQueue,
            curator: MemoryCurator,
            graph: GraphMemoryInterface,
            profiles: StudentProfileRepository,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
    ) -> MemoryIngestWorker:
        return MemoryIngestWorker(
            queue=queue,
            curator=curator,
            graph=graph,
            profiles=profiles,
            logger=logger,
            metrics=metrics_recorder,
            batch_size=settings.graph_memory_settings.ingest_batch_size,
            idle_sleep_sec=settings.graph_memory_settings.ingest_idle_sleep_sec,
        )

    @provide(scope=Scope.APP)
    def consolidation_worker(
            self,
            graph: GraphMemoryInterface,
            profiles: StudentProfileRepository,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
    ) -> MemoryConsolidationWorker:
        return MemoryConsolidationWorker(
            graph=graph,
            profiles=profiles,
            logger=logger,
            metrics=metrics_recorder,
            interval_sec=settings.graph_memory_settings.consolidation_interval_sec,
            first_delay_sec=settings.graph_memory_settings.consolidation_first_delay_sec,
            max_students=settings.graph_memory_settings.consolidation_max_students,
        )


GraphMemoryProviders = [
    GraphMemoryProvider(),
    MemoryEpisodeQueueProvider(),
    MemoryCuratorProvider(),
    GraphMemoryWorkersProvider(),
]
