import logging

from jwt.api_jwt import decode

from task_service.app.application.interfaces.services.token_service import (
    TokenServiceInterface
)
from task_service.app.config import Settings


class TokenService(TokenServiceInterface):
    def __init__(self, settings: Settings, logger: logging.Logger):
        self.settings = settings
        self.logger = logger

    def decode_token(self, token: str) -> int | None:
        try:
            payload = decode(
                token,
                self.settings.token_settings.secret_key,
                algorithms=[self.settings.token_settings.algorithm],
            )
            if payload.get("typ") != "access":
                return None
            return payload["user_id"]

        except Exception:
            self.logger.exception("Failed to decode token")
            return None
