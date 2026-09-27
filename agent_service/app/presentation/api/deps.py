import logging

from fastapi import HTTPException, status
from jwt.api_jwt import decode
from starlette.requests import Request

from agent_service.app.config import Settings

_logger = logging.getLogger(__name__)


def get_current_user_id_or_401(request: Request, settings: Settings) -> str:
    authorization = request.headers.get("Authorization") or ""
    if authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if settings.token_settings.secret_key.strip():
            user_id = _decode_user_id(token, settings)
            if user_id is not None:
                return str(user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Невалидный или истекший токен",
                headers={"WWW-Authenticate": "Bearer"},
            )

    header_user = (request.headers.get("X-User-Id") or "").strip()
    if (
        header_user
        and not settings.token_settings.secret_key.strip()
        and bool(getattr(settings.token_settings, "allow_dev_auth", False))
    ):
        return header_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется авторизация",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_user_id(token: str, settings: Settings) -> int | None:
    try:
        payload = decode(
            token,
            settings.token_settings.secret_key,
            algorithms=[settings.token_settings.algorithm or "HS256"],
        )
        if payload.get("typ") != "access":
            return None
        raw = payload.get("user_id")
        if raw is None:
            return None
        return int(raw)
    except Exception:
        _logger.info("Failed to decode chat auth token", exc_info=True)
        return None
