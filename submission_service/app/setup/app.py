import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from submission_service.app.config import Settings
from submission_service.app.setup.ioc import create_container
from submission_service.app.infrastructure.logger.setup_logging import setup_logging
from submission_service.app.infrastructure.kafka import (
    run_review_completed_consumer,
    run_task_events_consumer,
)
from submission_service.app.application.interfaces.kafka import SubmissionEventProducerInterface
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.presentation.api.healthcheck import router as healthcheck_router
from submission_service.app.presentation.api.exception_handler import setup_error_handlers
from submission_service.app.presentation.api.v1.router import router as v1_router
from monitoring_python.fastapi_observability import configure_observability


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container = app.state.dishka_container
    settings = await container.get(Settings)
    logger = await container.get(logging.Logger)
    producer = await container.get(SubmissionEventProducerInterface)
    await producer.start()
    task_cache = await container.get(TaskCacheInterface)
    review_consumer_task = asyncio.create_task(
        run_review_completed_consumer(settings, container, logger),
    )
    task_events_consumer_task = asyncio.create_task(
        run_task_events_consumer(settings, task_cache, logger),
    )
    app.state.kafka_review_consumer_task = review_consumer_task
    app.state.kafka_task_events_consumer_task = task_events_consumer_task
    yield
    review_consumer_task.cancel()
    task_events_consumer_task.cancel()
    try:
        await review_consumer_task
    except asyncio.CancelledError:
        pass
    try:
        await task_events_consumer_task
    except asyncio.CancelledError:
        pass
    await producer.stop()
    await container.close()


def create_app() -> FastAPI:
    settings = Settings()
    setup_logging(settings)

    app = FastAPI(
        root_path="/api",
        title="Submissions Service API",
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

    app.include_router(v1_router, prefix="/submission/v1")
    app.include_router(healthcheck_router, prefix="/submission/health")

    configure_observability(app, service_name="submission-service")

    return app


app = create_app()
