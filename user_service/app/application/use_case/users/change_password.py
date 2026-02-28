from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.interfaces.register.password_service import PasswordServiceInterface


class ChangePasswordUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryInterface,
        password_service: PasswordServiceInterface,
    ) -> None:
        self.user_repo = user_repo
        self.password_service = password_service

    async def __call__(
        self,
        user_id: int,
        *,
        current_password: str,
        new_password: str,
    ) -> bool | str:
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            return "user_not_found"

        if not self.password_service.verify_password(current_password, user.password):
            return "wrong_password"

        new_hash = self.password_service.hash_password(new_password)
        return await self.user_repo.update_password(user_id, new_hash)
