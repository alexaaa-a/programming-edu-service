import asyncio
import logging
from collections.abc import Iterable
from contextlib import asynccontextmanager

import aiohttp
from aiohttp import ClientTimeout
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import HttpUrl
from starlette.responses import Response

from api_gateway.app.config import Settings

logger = logging.getLogger(__name__)


def _select_backend_base_url(api_prefix: str, path: str, settings: Settings) -> HttpUrl | None:
    if not path.startswith(api_prefix.rstrip("/")):
        return None

    trimmed = path[len(api_prefix.rstrip("/")) :].lstrip("/")
    if not trimmed:
        return None

    segment = trimmed.split("/", 1)[0]
    mapping: dict[str, str] = {
        "user": settings.user_service_url,
        "task": settings.task_service_url,
        "submission": settings.submission_service_url,
        "agents": settings.agent_service_url,
    }
    base_url = mapping.get(segment)
    return HttpUrl(base_url) if base_url else None


def _forward_headers(request: Request, *, client_host: str | None) -> dict[str, str]:
    excluded = {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }

    headers: dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() in excluded:
            continue
        headers[k] = v

    if client_host:
        headers["X-Forwarded-For"] = client_host
    headers.setdefault("X-Forwarded-Proto", request.url.scheme)
    return headers


async def _proxy_request(
    *,
    request: Request,
    backend_base_url: HttpUrl,
    session: aiohttp.ClientSession,
    timeout: ClientTimeout,
) -> Response:
    backend_url = f"{str(backend_base_url).rstrip('/')}{request.url.path}"
    query_params = list(request.query_params.multi_items())

    body = await request.body()
    data: bytes | None = body if body else None

    client_host = request.client.host if request.client else None
    headers = _forward_headers(request, client_host=client_host)

    async with session.request(
        method=request.method,
        url=backend_url,
        params=query_params or None,
        data=data,
        headers=headers,
        timeout=timeout,
    ) as resp:
        resp_body = await resp.read()

        excluded = {
            "content-length",
            "transfer-encoding",
            "connection",
            "keep-alive",
        }
        response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}

        return Response(
            content=resp_body,
            status_code=resp.status,
            headers=response_headers,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> Iterable[None]:
    settings: Settings = app.state.settings
    timeout = ClientTimeout(total=float(settings.proxy_timeout_sec))

    async with aiohttp.ClientSession(timeout=timeout) as session:
        app.state.http_session = session
        app.state.proxy_timeout = timeout
        yield


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        root_path="",
        title="API Gateway",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    logging.basicConfig(level=logging.INFO)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.api_route(
        "/api/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        response_model=None,
    )
    async def gateway_router(request: Request, full_path: str) -> Response:
        backend = _select_backend_base_url(settings.api_prefix, request.url.path, settings)
        if backend is None:
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        try:
            timeout: ClientTimeout = app.state.proxy_timeout
            session: aiohttp.ClientSession = app.state.http_session
            return await _proxy_request(
                request=request,
                backend_base_url=backend,
                session=session,
                timeout=timeout,
            )
        except asyncio.TimeoutError:  # pragma: no cover
            return JSONResponse({"detail": "Gateway timeout"}, status_code=504)
        except Exception as e:
            logger.exception("gateway.proxy.error path=%s err=%s", request.url.path, e)
            return JSONResponse({"detail": "Bad Gateway"}, status_code=502)

    return app


app = create_app()
