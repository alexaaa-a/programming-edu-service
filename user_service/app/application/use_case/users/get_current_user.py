from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.dto import UserShowDTO


class GetCurrentUserUseCase:
    def __init__(self, user_repo: UserRepositoryInterface):
        self.user_repo = user_repo

    async def __call__(self, user_id: int) -> UserShowDTO | None:
        curr_user = await self.user_repo.get_user_by_id(user_id)

        if curr_user is None:
            return None

        return UserShowDTO(
            username=curr_user.username,
            name=curr_user.name,
            surname=curr_user.surname,
            level=curr_user.level,
            direction=curr_user.direction,
            email=curr_user.email,
        )
