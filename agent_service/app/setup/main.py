import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_service.app.infrastructure.kafka import SubmissionReviewConsumer
from agent_service.app.infrastructure.logger import setup_logging
from agent_service.app.config import Settings
from agent_service.app.presentation.api.exception_handler import setup_error_handlers
from agent_service.app.presentation.api.healthcheck import router as healthcheck_router
from agent_service.app.presentation.api.metrics import router as metrics_router
from agent_service.app.presentation.api.v1.router import router as v1_router
from agent_service.app.setup.ioc import create_container
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.use_cases import EvaluateRagSearchUseCase
from agent_service.app.application.observability.tracing import reset_trace_id, set_trace_id
from agent_service.app.infrastructure.memory.knowledge_base_indexer import (
    KnowledgeBaseIndexingConfig,
    index_knowledge_base,
)
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container = app.state.dishka_container
    logger: logging.Logger = await container.get(logging.Logger)
    logger.info("Agent service startup")

    memory: MemoryInterface = await container.get(MemoryInterface)
    knowledge_dir = Path(__file__).resolve().parents[1] / "infrastructure" / "knowledge"
    flag_path = (
        Path(__file__).resolve().parents[1]
        / "infrastructure"
        / "vector_store_data"
        / "knowledge_indexed.flag"
    )
    await index_knowledge_base(
        memory=memory,
        config=KnowledgeBaseIndexingConfig(
            knowledge_dir=knowledge_dir,
            flag_path=flag_path,
        ),
    )

    try:
        rag_eval_use_case = await container.get(EvaluateRagSearchUseCase)
        await rag_eval_use_case()
    except Exception:
        logger.exception("rag.eval failed during startup")

    consumer = await container.get(SubmissionReviewConsumer)
    consumer_task = asyncio.create_task(consumer.run())
    app.state.kafka_submission_review_task = consumer_task

    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("Agent service shutdown")
        await container.close()


def create_app() -> FastAPI:
    settings = Settings()
    setup_logging(settings)

    app = FastAPI(
        root_path="/api",
        title="Agent Service API",
        lifespan=lifespan,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    setup_error_handlers(app)
    container = create_container(settings)
    setup_dishka(container, app)

    @app.middleware("http")
    async def tracing_middleware(request: Request, call_next):
        header_trace_id = request.headers.get("X-Trace-Id")
        trace_id = header_trace_id.strip() if header_trace_id else uuid4().hex
        token = set_trace_id(trace_id)
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            reset_trace_id(token)

    app.include_router(healthcheck_router, prefix="/agents/health")
    app.include_router(v1_router, prefix="/agents/v1")
    app.include_router(metrics_router, prefix="/agents")

    return app


app = create_app()
