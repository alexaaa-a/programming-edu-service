import logging

from motor.motor_asyncio import AsyncIOMotorClient
from typing import Any

from user_service.app.application.dto import UserDTO
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.config import Settings


class UserRepository(UserRepositoryInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger
    ):
        self._client = client[settings.mongo_settings.name]
        self._settings = settings
        self.db = self._client["users"]
        self.logger = logger

    async def get_user_by_id(self, user_id: int) -> UserDTO | None:
        try:
            doc = await self.db.find_one({"user_id": user_id})
            if doc is None:
                return None
            data = {k: v for k, v in doc.items() if k != "_id"}
            data.setdefault("direction", None)
            data.setdefault("level", None)
            return UserDTO(**data)

        except Exception:
            self.logger.exception(f"Failed to get user by id {user_id}")
            return None

    async def get_user_by_email(self, email: str) -> UserDTO | None:
        try:
            doc = await self.db.find_one({"email": email})
            if doc is None:
                return None
            data = {k: v for k, v in doc.items() if k != "_id"}
            data.setdefault("direction", None)
            data.setdefault("level", None)
            return UserDTO(**data)

        except Exception:
            self.logger.exception(f"Failed to get user by email")
            return None

    async def create_or_update_user(self, user: UserDTO) -> bool:
        try:
            await self.db.update_one(
                {"user_id": user.user_id},
                {"$set": {
                    "user_id": user.user_id,
                    "name": user.name,
                    "surname": user.surname,
                    "username": user.username,
                    "email": user.email,
                    "password": user.password,
                    "direction": user.direction,
                    "level": user.level,
                }},
                upsert=True
            )
            return True

        except Exception:
            self.logger.exception(f"Failed to create or update user by id {user.user_id}")
            return False

    async def update_profile(
        self,
        user_id: int,
        *,
        name: str | None = None,
        surname: str | None = None,
        username: str | None = None,
        email: str | None = None,
        direction: str | None = None,
        level: str | None = None,
    ) -> bool:
        try:
            update: dict = {}
            if name is not None:
                update["name"] = name
            if surname is not None:
                update["surname"] = surname
            if username is not None:
                update["username"] = username
            if email is not None:
                update["email"] = email
            if direction is not None:
                update["direction"] = direction
            if level is not None:
                update["level"] = level
            if not update:
                return True
            result = await self.db.update_one(
                {"user_id": user_id},
                {"$set": update},
            )
            return result.modified_count > 0 or result.matched_count > 0
        except Exception:
            self.logger.exception(f"Failed to update profile for user_id={user_id}")
            return False

    async def update_password(self, user_id: int, new_password_hash: str) -> bool:
        try:
            result = await self.db.update_one(
                {"user_id": user_id},
                {"$set": {"password": new_password_hash}},
            )
            return result.modified_count > 0 or result.matched_count > 0
        except Exception:
            self.logger.exception(f"Failed to update password for user_id={user_id}")
            return False
