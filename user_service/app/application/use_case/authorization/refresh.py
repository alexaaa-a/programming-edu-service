from user_service.app.application.dto import AuthResultDTO
from user_service.app.application.interfaces.db.session_repo import SessionRepositoryInterface
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.interfaces.register.token_service import TokenServiceInterface


class RefreshUseCase:
    def __init__(
            self,
            session_repo: SessionRepositoryInterface,
            user_repo: UserRepositoryInterface,
            token_service: TokenServiceInterface,
    ) -> None:
        self.session_repo = session_repo
        self.user_repo = user_repo
        self.token_service = token_service

    async def __call__(self, refresh_token: str) -> AuthResultDTO:
        user_id = self.token_service.decode_refresh_token(refresh_token)
        if not user_id:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        stored_refresh = await self.session_repo.get_refresh_token(user_id)
        if stored_refresh is None or stored_refresh != refresh_token:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        user_db = await self.user_repo.get_user_by_id(user_id)
        if not user_db:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        access = self.token_service.create_token(user_id, "access")
        return AuthResultDTO(
            access_token=access,
            refresh_token=refresh_token,
            is_email_exists=False,
        )
