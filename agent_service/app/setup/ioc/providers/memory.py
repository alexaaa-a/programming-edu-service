import logging
from collections.abc import AsyncIterable
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI
from dishka import Provider, Scope, provide

from agent_service.app.application.interfaces import (
    ChatHistoryRepository,
    DecisionModelInterface,
    LLMInterface,
    MemoryInterface,
    RetrieveCache,
    StudentProfileRepository,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.llm_trace import LlmTracer
from agent_service.app.config import Settings
from agent_service.app.infrastructure.llm import OpenAIClient
from agent_service.app.infrastructure.memory.cached_retrieve_memory import CachedMemory
from agent_service.app.infrastructure.memory.embedding_service import build_embedding_service
from agent_service.app.infrastructure.memory.layered_memory import LayeredMemory, build_layered_stores
from agent_service.app.infrastructure.chat_history.mongo_chat_history_repository import (
    MongoChatHistoryRepository,
)
from agent_service.app.infrastructure.student_profile import MongoStudentProfileRepository


class LLMProvider(Provider):
    @provide(scope=Scope.APP, provides=LLMInterface)
    def llm(
            self,
            openai_client: AsyncOpenAI,
            settings: Settings,
            logger: logging.Logger,
            metrics_recorder: MetricsRecorder,
            tracer: LlmTracer,
    ) -> LLMInterface:
        return OpenAIClient(
            client=openai_client,
            settings=settings.openai_settings,
            logger=logger,
            metrics=metrics_recorder,
            tracer=tracer,
        )


class MemoryProvider(Provider):
    @provide(scope=Scope.APP, provides=MemoryInterface)
    def memory(
            self,
            openai_client: AsyncOpenAI,
            metrics_recorder: MetricsRecorder,
            chat_history_repository: ChatHistoryRepository,
            retrieve_cache: RetrieveCache,
            settings: Settings,
            logger: logging.Logger,
            tracer: LlmTracer,
            decisions: DecisionModelInterface,
    ) -> MemoryInterface:
        embeddings = build_embedding_service(
            backend=settings.memory_settings.embedding_backend,
            client=_embedding_client(openai_client, settings),
            model=settings.openai_settings.embedding_model,
            logger=logger,
        )
        persist_dir = Path(settings.memory_settings.persist_dir)
        stores = build_layered_stores(
            embeddings=embeddings,
            persist_dir=persist_dir,
            metrics_recorder=metrics_recorder,
        )
        layered = LayeredMemory(
            stores=stores,
            embeddings=embeddings,
            chat_history_repository=chat_history_repository,
            metrics_recorder=metrics_recorder,
            logger=logger,
            max_retrieve_top_k=settings.memory_settings.max_retrieve_top_k,
            tracer=tracer,
            decisions=decisions,
            min_confidence=settings.jev_settings.min_confidence,
            dedup_similarity=settings.memory_settings.dedup_similarity,
            rerank_enabled=settings.jev_settings.rerank_enabled,
            write_gate_enabled=settings.jev_settings.write_gate_enabled,
            reinforce_enabled=settings.memory_settings.reinforce_enabled,
        )
        return CachedMemory(
            inner=layered,
            retrieve_cache=retrieve_cache,
            ttl_sec=settings.redis_settings.retrieve_cache_ttl_sec,
            cache_version=f"layers-{embeddings.name}",
            logger=logger,
            metrics_recorder=metrics_recorder,
        )


class MongoClientProvider(Provider):
    @provide(scope=Scope.APP)
    async def mongo_client(self, settings: Settings) -> AsyncIterable[AsyncIOMotorClient]:
        client = AsyncIOMotorClient(
            str(settings.mongo_settings.connection_string),
            maxIdleTimeMS=settings.mongo_settings.server_selection_timeout_ms,
        )
        try:
            yield client
        finally:
            client.close()


class ChatHistoryRepositoryProvider(Provider):
    @provide(scope=Scope.APP, provides=ChatHistoryRepository)
    async def chat_history_repository(
            self,
            mongo_client: AsyncIOMotorClient,
            settings: Settings,
    ) -> ChatHistoryRepository:
        collection = mongo_client[settings.mongo_settings.name]["chat_messages"]
        await collection.create_index([("thread_id", 1), ("timestamp", 1), ("order", 1)])
        return MongoChatHistoryRepository(
            collection,
            max_messages=settings.chat_history_settings.max_messages,
        )


class StudentProfileRepositoryProvider(Provider):
    @provide(scope=Scope.APP, provides=StudentProfileRepository)
    async def student_profile_repository(
            self,
            mongo_client: AsyncIOMotorClient,
            settings: Settings,
    ) -> StudentProfileRepository:
        collection = mongo_client[settings.mongo_settings.name]["student_profiles"]
        await collection.create_index("user_id", unique=True)
        return MongoStudentProfileRepository(collection)


def _embedding_client(openai_client: AsyncOpenAI, settings: Settings) -> AsyncOpenAI:
    extra = (settings.openai_settings.embedding_base_url or "").strip()
    if not extra:
        return openai_client
    return AsyncOpenAI(
        api_key=(settings.openai_settings.embedding_api_key or settings.openai_settings.api_key),
        base_url=extra.rstrip("/"),
        timeout=settings.openai_settings.timeout_sec,
    )


MemoryProviders = [
    LLMProvider(),
    MemoryProvider(),
    MongoClientProvider(),
    ChatHistoryRepositoryProvider(),
    StudentProfileRepositoryProvider(),
]
