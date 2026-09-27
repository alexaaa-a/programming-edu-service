import datetime
import logging

from jwt.api_jwt import encode, decode

from user_service.app.application.interfaces.register.token_service import (
    TokenServiceInterface,
)
from user_service.app.config import Settings

_ACCESS = "access"
_REFRESH = "refresh"


class JWTTokenService(TokenServiceInterface):
    def __init__(self, settings: Settings, logger: logging.Logger):
        self.settings = settings
        self.logger = logger

    def create_token(self, user_id: int, token_type: str) -> str:
        kind = _REFRESH if token_type == _REFRESH else _ACCESS
        exp_time = (
            self.settings.register_settings.ttl_refresh
            if kind == _REFRESH
            else self.settings.register_settings.access_token_expire
        )
        expire = datetime.datetime.now() + datetime.timedelta(
            seconds=exp_time
        )
        payload = {"user_id": user_id, "exp": expire, "typ": kind}
        token = encode(
            payload,
            self.settings.register_settings.secret_key,
            algorithm=self.settings.register_settings.algorithm
        )

        return token

    def decode_token(self, token: str) -> int | None:
        return self._decode(token, expected=_ACCESS)

    def decode_refresh_token(self, token: str) -> int | None:
        return self._decode(token, expected=_REFRESH)

    def _decode(self, token: str, expected: str) -> int | None:
        try:
            payload = decode(
                token,
                self.settings.register_settings.secret_key,
                algorithms=[self.settings.register_settings.algorithm],
            )
            typ = payload.get("typ")
            if typ != expected:
                return None
            return payload["user_id"]

        except Exception:
            self.logger.exception("Failed to decode token")
            return None
