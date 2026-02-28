from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from user_service.app.config import Settings
from user_service.app.setup.ioc import create_container
from user_service.app.infrastructure.logger import setup_logging
from user_service.app.presentation.api.healthcheck import router as healthcheck_router
from user_service.app.presentation.api.exception_handler import setup_error_handlers
from user_service.app.presentation.api.v1.app import app as app_v1


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await app.state.dishka_container.close()


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

    app.mount("/v1", app_v1)
    app.include_router(healthcheck_router, prefix="/health")

    return app

app = create_app()
