import aiohttp
from dishka import Provider, Scope, provide
import logging

from agent_service.app.application.interfaces import (
    ChatHistoryRepository,
    LLMInterface,
    MemoryInterface,
    RetrieveCache,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.config import Settings
from agent_service.app.infrastructure.llm import OpenRouterClient
from agent_service.app.infrastructure.memory.rag_memory import RagMemory
from agent_service.app.infrastructure.memory.cached_retrieve_memory import CachedMemory
from agent_service.app.infrastructure.chat_history.tinydb_chat_history_repository import (
    TinyDbChatHistoryConfig,
    TinyDbChatHistoryRepository,
)


class LLMProvider(Provider):
    @provide(scope=Scope.APP, provides=LLMInterface)
    def llm(
        self,
        aiohttp_client_session: aiohttp.ClientSession,
        settings: Settings,
        logger: logging.Logger,
        metrics_recorder: MetricsRecorder,
    ) -> LLMInterface:
        return OpenRouterClient(
            session=aiohttp_client_session,
            settings=settings.openrouter_settings,
            logger=logger,
            metrics=metrics_recorder,
        )


class MemoryProvider(Provider):
    @provide(scope=Scope.APP, provides=MemoryInterface)
    def memory(
        self,
        metrics_recorder: MetricsRecorder,
        chat_history_repository: ChatHistoryRepository,
        retrieve_cache: RetrieveCache,
        settings: Settings,
        logger: logging.Logger,
    ) -> MemoryInterface:
        rag_memory: MemoryInterface = RagMemory(
            metrics_recorder=metrics_recorder,
            chat_history_repository=chat_history_repository,
            logger=logger,
        )
        return CachedMemory(
            inner=rag_memory,
            retrieve_cache=retrieve_cache,
            ttl_sec=settings.redis_settings.retrieve_cache_ttl_sec,
            logger=logger,
            metrics_recorder=metrics_recorder,
        )
 
class ChatHistoryRepositoryProvider(Provider):
    @provide(scope=Scope.APP, provides=ChatHistoryRepository)
    def chat_history_repository(
        self,
        settings: Settings,
    ) -> ChatHistoryRepository:
        return TinyDbChatHistoryRepository(
            db_path=settings.tinydb_settings.chat_history_path,
            config=TinyDbChatHistoryConfig(
                max_messages=settings.chat_history_settings.max_messages,
            ),
        )


MemoryProviders = [LLMProvider(), MemoryProvider(), ChatHistoryRepositoryProvider()]
