import asyncio
import logging
import os
from typing import Any

from openai import AsyncOpenAI
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder import OpenAIEmbedder
from graphiti_core.embedder.openai import OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMConfig, OpenAIClient

from agent_service.app.config import GraphMemorySettings, Neo4jSettings, OpenAISettings


def graphiti_available() -> bool:
    try:
        import graphiti_core  # noqa: F401
    except Exception:
        return False
    return True


def _silence_telemetry() -> None:
    os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")


def build_graphiti(
        neo4j: Neo4jSettings,
        graph_memory: GraphMemorySettings,
        openai_settings: OpenAISettings,
        llm_client: AsyncOpenAI,
        embedding_client: AsyncOpenAI,
        logger: logging.Logger,
) -> Any | None:
    if not graph_memory.enabled:
        logger.info("graph_memory.disabled reason=flag")
        return None
    if not neo4j.is_configured:
        logger.info("graph_memory.disabled reason=no_neo4j_uri")
        return None
    _silence_telemetry()

    config = LLMConfig(
        api_key=openai_settings.api_key,
        model=graph_memory.extraction_model or openai_settings.model,
        base_url=openai_settings.base_url,
        temperature=0.0,
    )
    driver = None
    try:
        llm = OpenAIClient(config=config, client=llm_client)
        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                embedding_model=openai_settings.embedding_model,
                embedding_dim=graph_memory.embedding_dim,
                api_key=openai_settings.api_key,
                base_url=openai_settings.base_url,
            ),
            client=embedding_client,
        )
        cross_encoder = OpenAIRerankerClient(config=config, client=llm_client)

        driver = Neo4jDriver(
            uri=neo4j.uri,
            user=neo4j.user,
            password=neo4j.password,
            database=neo4j.database or "neo4j",
        )
        client = Graphiti(
            graph_driver=driver,
            llm_client=llm,
            embedder=embedder,
            cross_encoder=cross_encoder,
            store_raw_episode_content=False,
            max_coroutines=graph_memory.max_coroutines,
        )
    except Exception:
        logger.exception("graph_memory.client_failed")
        _close_quietly(driver, logger)
        return None

    logger.info(
        "graph_memory.enabled uri=%s database=%s model=%s",
        neo4j.safe_uri,
        neo4j.database,
        graph_memory.extraction_model or openai_settings.model,
    )
    return client


def _close_quietly(driver: Any | None, logger: logging.Logger) -> None:
    if driver is None:
        return
    close = getattr(driver, "close", None)
    if close is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_await_close(close, logger))
    task.add_done_callback(lambda _: None)


async def _await_close(close: Any, logger: logging.Logger) -> None:
    try:
        result = close()
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        logger.debug("graph_memory.driver_close_failed", exc_info=True)
