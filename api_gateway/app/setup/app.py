import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Iterable
from contextlib import asynccontextmanager
from hashlib import md5

import aiohttp
import redis.asyncio as redis
from aiohttp import ClientTimeout
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from api_gateway.app.config import Settings
from monitoring_python.fastapi_observability import configure_observability

logger = logging.getLogger(__name__)


class ServiceRouter:
    def __init__(self, settings: Settings) -> None:
        self._api_prefix = settings.api_prefix.rstrip("/") or "/api"
        self._mapping: dict[str, list[str]] = {
            "user": [s.strip() for s in settings.user_service_url.split(",") if s.strip()],
            "task": [s.strip() for s in settings.task_service_url.split(",") if s.strip()],
            "submission": [s.strip() for s in settings.submission_service_url.split(",") if s.strip()],
            "agents": [s.strip() for s in settings.agent_service_url.split(",") if s.strip()],
        }

    def route(self, path: str) -> tuple[str, list[str]] | None:
        if not path.startswith(self._api_prefix):
            return None

        trimmed = path[len(self._api_prefix):].lstrip("/")
        if not trimmed:
            return None
        segment = trimmed.split("/", 1)[0]
        targets = self._mapping.get(segment)
        if not targets:
            return None
        return segment, targets

    @property
    def api_prefix(self) -> str:
        return self._api_prefix


class RoundRobinBalancer:
    def __init__(self) -> None:
        self._indices: dict[str, int] = defaultdict(int)

    def pick(self, service_key: str, targets: list[str]) -> str:
        if len(targets) == 1:
            return targets[0]
        idx = self._indices[service_key] % len(targets)
        self._indices[service_key] = (idx + 1) % len(targets)
        return targets[idx]


class StickyBalancer:
    def __init__(self) -> None:
        self._rr = RoundRobinBalancer()

    def pick(
            self,
            service_key: str,
            targets: list[str],
            sticky_enabled: bool,
            sticky_key: str | None,
    ) -> str:
        if not sticky_enabled or not sticky_key or len(targets) <= 1:
            return self._rr.pick(service_key, targets)
        digest = md5(sticky_key.encode("utf-8")).hexdigest()
        idx = int(digest, 16) % len(targets)
        return targets[idx]


class InMemoryFixedWindowRateLimiter:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, max_requests: int, window_sec: int) -> tuple[bool, int]:
        if not self._enabled:
            return True, 0

        max_requests = max(1, max_requests)
        window_sec = max(1, window_sec)
        now = time.time()
        left = now - window_sec
        bucket = self._buckets[key]
        while bucket and bucket[0] < left:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = int(max(1, window_sec - (now - bucket[0])))
            return False, retry_after

        bucket.append(now)
        return True, 0


class RedisFixedWindowRateLimiter:
    KEY_PREFIX = "gateway:rate_limit"

    def __init__(self, client: redis.Redis, enabled: bool) -> None:
        self._client = client
        self._enabled = enabled

    async def allow(self, key: str, max_requests: int, window_sec: int) -> tuple[bool, int]:
        if not self._enabled:
            return True, 0

        max_requests = max(1, max_requests)
        window_sec = max(1, window_sec)
        redis_key = f"{self.KEY_PREFIX}:{key}"

        count = await self._client.incr(redis_key)
        if count == 1:
            await self._client.expire(redis_key, window_sec)
            return True, 0
        if count <= max_requests:
            return True, 0

        ttl = await self._client.ttl(redis_key)
        retry_after = int(ttl) if isinstance(ttl, int) and ttl > 0 else window_sec
        return False, retry_after


class CompositeRateLimiter:
    def __init__(
            self,
            memory: InMemoryFixedWindowRateLimiter,
            redis_limiter: RedisFixedWindowRateLimiter | None,
    ) -> None:
        self._memory = memory
        self._redis = redis_limiter

    async def allow(self, key: str, max_requests: int, window_sec: int) -> tuple[bool, int]:
        if self._redis is not None:
            try:
                return await self._redis.allow(
                    key,
                    max_requests=max_requests,
                    window_sec=window_sec,
                )
            except Exception:
                logger.exception("gateway.rate_limit.redis.error key=%s", key)
        return self._memory.allow(key, max_requests=max_requests, window_sec=window_sec)


def _forward_headers(request: Request, client_host: str | None) -> dict[str, str]:
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


def _parse_service_limit_overrides(raw: str) -> dict[str, int]:
    overrides: dict[str, int] = {}
    if not raw.strip():
        return overrides
    for part in raw.split(","):
        item = part.strip()
        if not item or ":" not in item:
            continue
        svc, limit_raw = item.split(":", 1)
        service_key = svc.strip()
        try:
            limit = int(limit_raw.strip())
        except ValueError:
            continue
        if service_key and limit > 0:
            overrides[service_key] = limit
    return overrides


def _sticky_key_from_request(request: Request, service_key: str) -> str | None:
    for header in ("X-User-Id", "X-Session-Id"):
        value = request.headers.get(header)
        if value:
            return f"{service_key}:{header}:{value}"
    auth = request.headers.get("Authorization")
    if auth:
        return f"{service_key}:auth:{auth}"
    client_host = request.client.host if request.client else None
    if client_host:
        return f"{service_key}:ip:{client_host}"
    return None


async def _proxy_request(
        request: Request,
        backend_base_url: str,
        backend_path: str,
        session: aiohttp.ClientSession,
        timeout: ClientTimeout,
) -> Response:
    backend_url = f"{backend_base_url.rstrip('/')}{backend_path}"
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
    redis_client: redis.Redis | None = None

    async with aiohttp.ClientSession(timeout=timeout) as session:
        if settings.rate_limit_redis_url:
            redis_client = redis.from_url(
                settings.rate_limit_redis_url,
                decode_responses=True,
            )
            try:
                await redis_client.ping()
            except Exception:
                logger.exception("gateway.rate_limit.redis_unavailable; fallback to memory")
                redis_client = None

        app.state.http_session = session
        app.state.proxy_timeout = timeout
        app.state.service_router = ServiceRouter(settings)
        app.state.load_balancer = StickyBalancer()
        app.state.rate_limit_window_sec = settings.rate_limit_window_sec
        app.state.rate_limit_default_max_requests = settings.rate_limit_max_requests
        app.state.rate_limit_service_overrides = _parse_service_limit_overrides(
            settings.rate_limit_service_max_requests,
        )
        app.state.sticky_enabled = settings.sticky_enabled
        app.state.rate_limiter = CompositeRateLimiter(
            memory=InMemoryFixedWindowRateLimiter(enabled=settings.rate_limit_enabled),
            redis_limiter=(
                RedisFixedWindowRateLimiter(redis_client, enabled=settings.rate_limit_enabled)
                if redis_client is not None
                else None
            ),
        )
        yield
        if redis_client is not None:
            await redis_client.close()


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
        service_router: ServiceRouter = app.state.service_router
        route = service_router.route(request.url.path)
        if route is None:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        service_key, targets = route

        client_host = request.client.host if request.client else "unknown"
        limiter: CompositeRateLimiter = app.state.rate_limiter
        overrides: dict[str, int] = app.state.rate_limit_service_overrides
        max_requests = overrides.get(service_key, app.state.rate_limit_default_max_requests)
        limit_key = f"{client_host}:{service_key}:{request.method}"
        allowed, retry_after = await limiter.allow(
            limit_key,
            max_requests=max_requests,
            window_sec=app.state.rate_limit_window_sec,
        )
        if not allowed:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        try:
            timeout: ClientTimeout = app.state.proxy_timeout
            session: aiohttp.ClientSession = app.state.http_session
            balancer: StickyBalancer = app.state.load_balancer
            backend = balancer.pick(
                service_key,
                targets,
                sticky_enabled=app.state.sticky_enabled,
                sticky_key=_sticky_key_from_request(request, service_key),
            )
            backend_path = request.url.path
            return await _proxy_request(
                request=request,
                backend_base_url=backend,
                backend_path=backend_path,
                session=session,
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return JSONResponse({"detail": "Gateway timeout"}, status_code=504)
        except Exception as e:
            logger.exception("gateway.proxy.error path=%s err=%s", request.url.path, e)
            return JSONResponse({"detail": "Bad Gateway"}, status_code=502)

    configure_observability(app, service_name="api-gateway")

    return app


app = create_app()
