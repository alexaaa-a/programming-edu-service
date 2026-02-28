from user_service.app.application.interfaces.db.session_repo import SessionRepositoryInterface
from user_service.app.application.interfaces.register.token_service import TokenServiceInterface
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface


class LogoutUseCase:
    def __init__(
            self,
            session_repo: SessionRepositoryInterface,
            token_service: TokenServiceInterface,
            user_repo: UserRepositoryInterface,
    ) -> None:
        self.session_repo = session_repo
        self.token_service = token_service
        self.user_repo = user_repo

    async def __call__(self, refresh_token: str) -> bool:
        user_id = self.token_service.decode_token(refresh_token)
        if not user_id:
            return False

        user_db = await self.user_repo.get_user_by_id(user_id)
        if not user_db:
            return False

        delete_refresh = await self.session_repo.delete_refresh_token(user_id)
        return delete_refresh
