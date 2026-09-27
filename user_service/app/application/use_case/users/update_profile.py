from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.interfaces.kafka import UserEventProducerInterface


class UpdateProfileUseCase:
    def __init__(
            self,
            user_repo: UserRepositoryInterface,
            user_event_producer: UserEventProducerInterface,
    ) -> None:
        self.user_repo = user_repo
        self.user_event_producer = user_event_producer

    async def __call__(
            self,
            user_id: int,
            name: str | None = None,
            surname: str | None = None,
            username: str | None = None,
            email: str | None = None,
            direction: str | None = None,
            level: str | None = None,
    ) -> bool | str:
        if email is not None:
            existing = await self.user_repo.get_user_by_email(email)
            if existing is not None and existing.user_id != user_id:
                return "email_taken"
        result = await self.user_repo.update_profile(
            user_id,
            name=name,
            surname=surname,
            username=username,
            email=email,
            direction=direction,
            level=level,
        )
        if result:
            updated_user = await self.user_repo.get_user_by_id(user_id)
            if updated_user:
                await self.user_event_producer.produce_user_profile_updated(
                    user_id=user_id,
                    direction=updated_user.direction,
                    level=updated_user.level,
                )
        return result
