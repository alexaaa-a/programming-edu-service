import redis.asyncio as redis
import logging

from user_service.app.application.interfaces.db.session_repo import SessionRepositoryInterface
from user_service.app.config import Settings


class RedisSessionRepository(SessionRepositoryInterface):
    def __init__(
            self,
            redis_client: redis.Redis,
            logger: logging.Logger,
            settings: Settings
    ) -> None:
        self.redis_client = redis_client
        self.logger = logger
        self.settings = settings

    async def save_refresh_token(self, refresh_token: str, user_id: int) -> bool:
        key = f"refresh_token:{user_id}"

        try:
            await self.redis_client.set(
                key,
                refresh_token,
                self.settings.register_settings.ttl_refresh
            )
            return True

        except Exception:
            self.logger.exception("Exception when saving refresh token")
            return False

    async def get_refresh_token(self, user_id: int) -> str | None:
        key = f"refresh_token:{user_id}"

        try:
            data = await self.redis_client.get(key)

            if data is None:
                return None

            if isinstance(data, bytes):
                return data.decode("utf-8")
            return str(data) if data is not None else None

        except Exception:
            self.logger.exception("Exception when getting refresh token")
            return None

    async def delete_refresh_token(self, user_id: int) -> bool:
        key = f"refresh_token:{user_id}"

        try:
            await self.redis_client.delete(key)
            return True

        except Exception:
            self.logger.exception("Exception when deleting refresh token")
            return False
