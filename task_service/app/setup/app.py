import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from task_service.app.config import Settings
from task_service.app.setup.ioc import create_container
from task_service.app.infrastructure.logger.setup_logging import setup_logging
from task_service.app.infrastructure.kafka import run_user_events_consumer
from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface
from task_service.app.application.interfaces.kafka import TaskEventProducerInterface
from task_service.app.presentation.api.healthcheck import router as healthcheck_router
from task_service.app.presentation.api.exception_handler import setup_error_handlers
from task_service.app.presentation.api.v1.router import router as v1_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container = app.state.dishka_container
    settings = await container.get(Settings)
    logger = await container.get(logging.Logger)
    meta_user_db = await container.get(MetaUserDBInterface)
    task_producer = await container.get(TaskEventProducerInterface)
    await task_producer.start()
    consumer_task = asyncio.create_task(
        run_user_events_consumer(settings, meta_user_db, logger),
    )
    app.state.kafka_consumer_task = consumer_task
    yield
    consumer_task.cancel()
    await task_producer.stop()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await container.close()


def create_app() -> FastAPI:
    settings = Settings()
    setup_logging(settings)

    app = FastAPI(
        root_path="/api",
        title="Task Service API",
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

    app.include_router(v1_router, prefix="/task/v1")
    app.include_router(healthcheck_router, prefix="/task/health")

    return app


app = create_app()
