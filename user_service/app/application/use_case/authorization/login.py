from user_service.app.application.interfaces.register.password_service import PasswordServiceInterface
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.interfaces.register.token_service import TokenServiceInterface
from user_service.app.application.interfaces.db.session_repo import SessionRepositoryInterface
from user_service.app.application.dto.user import UserLoginDTO
from user_service.app.application.dto.auth import AuthResultDTO


class LoginUseCase:
    def __init__(
            self,
            password_service: PasswordServiceInterface,
            user_repo: UserRepositoryInterface,
            token_service: TokenServiceInterface,
            session_repo: SessionRepositoryInterface,
    ) -> None:
        self.password_service = password_service
        self.user_repo = user_repo
        self.token_service = token_service
        self.session_repo = session_repo

    async def __call__(self, user: UserLoginDTO) -> AuthResultDTO:
        user_db = await self.user_repo.get_user_by_email(user.email)
        if not user_db:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        check_password = self.password_service.verify_password(
            password=user.password,
            hashed_password=user_db.password
        )

        if not check_password:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        access = self.token_service.create_token(user_db.user_id, "access")
        refresh = self.token_service.create_token(user_db.user_id, "refresh")

        save_refresh = await self.session_repo.save_refresh_token(refresh, user_db.user_id)
        if not save_refresh:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        return AuthResultDTO(
            access_token=access,
            refresh_token=refresh,
            is_email_exists=False,
        )
