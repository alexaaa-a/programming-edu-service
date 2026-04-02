import json
import logging

import redis.asyncio as redis

from user_service.app.application.dto import AdminDTO
from user_service.app.application.interfaces.db.admin_cache_repo import (
    AdminCacheRepositoryInterface,
)


class AdminCacheRepository(AdminCacheRepositoryInterface):
    CACHE_KEY = "admins:list"
    TTL_SECONDS = 300

    def __init__(self, redis_client: redis.Redis, logger: logging.Logger) -> None:
        self.redis_client = redis_client
        self.logger = logger

    async def get_all_admins(self) -> list[AdminDTO] | None:
        try:
            raw = await self.redis_client.get(self.CACHE_KEY)
            if raw is None:
                return None

            data = json.loads(raw)
            if not isinstance(data, list):
                return None

            result: list[AdminDTO] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                user_id = item.get("user_id")
                role = item.get("role")
                if isinstance(user_id, int) and isinstance(role, str):
                    result.append(AdminDTO(user_id=user_id, role=role))
            return result
        except Exception:
            self.logger.exception("Failed to read admins cache")
            return None

    async def set_all_admins(self, admins: list[AdminDTO]) -> bool:
        try:
            payload = [{"user_id": a.user_id, "role": a.role} for a in admins]
            await self.redis_client.set(
                self.CACHE_KEY,
                json.dumps(payload, ensure_ascii=False),
                ex=self.TTL_SECONDS,
            )
            return True
        except Exception:
            self.logger.exception("Failed to write admins cache")
            return False
