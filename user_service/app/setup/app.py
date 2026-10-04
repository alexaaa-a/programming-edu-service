from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from user_service.app.config import Settings
from user_service.app.setup.ioc import create_container
from user_service.app.infrastructure.logger import setup_logging
from user_service.app.application.interfaces.kafka import UserEventProducerInterface
from user_service.app.presentation.api.healthcheck import router as healthcheck_router
from user_service.app.presentation.api.exception_handler import setup_error_handlers
from user_service.app.presentation.api.v1.router import router as v1_router
from monitoring_python.fastapi_observability import configure_observability


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container = app.state.dishka_container
    producer = await container.get(UserEventProducerInterface)
    await producer.start()
    yield
    await producer.stop()
    await container.close()


def create_app() -> FastAPI:
    settings = Settings()
    setup_logging(settings)

    app = FastAPI(
        root_path="/api",
        title="API сервиса обучения программированию",
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

    app.include_router(v1_router, prefix="/user/v1")
    app.include_router(healthcheck_router, prefix="/user/health")

    configure_observability(app, service_name="user-service")

    return app

app = create_app()
