import uuid

from user_service.app.application.dto import AuthResultDTO, UserDTO, UserRegisterDTO
from user_service.app.application.interfaces.db.session_repo import SessionRepositoryInterface
from user_service.app.application.interfaces.db.user_repo import UserRepositoryInterface
from user_service.app.application.interfaces.kafka import UserEventProducerInterface
from user_service.app.application.interfaces.register.password_service import PasswordServiceInterface
from user_service.app.application.interfaces.register.token_service import TokenServiceInterface


class RegisterUseCase:
    def __init__(
            self,
            user_repo: UserRepositoryInterface,
            password_service: PasswordServiceInterface,
            token_service: TokenServiceInterface,
            session_repo: SessionRepositoryInterface,
            user_event_producer: UserEventProducerInterface,
    ) -> None:
        self.user_repo = user_repo
        self.password_service = password_service
        self.token_service = token_service
        self.session_repo = session_repo
        self.user_event_producer = user_event_producer

    async def __call__(self, user: UserRegisterDTO) -> AuthResultDTO:
        user_db = await self.user_repo.get_user_by_email(user.email)
        if user_db:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=True,
            )

        password_hash = self.password_service.hash_password(user.password)
        user_id = self._generate_user_id()
        user = UserDTO(
            user_id=user_id,
            name=user.name,
            surname=user.surname,
            email=user.email,
            password=password_hash,
            username=user.username,
            direction=None,
            level=None,
        )

        save_user = await self.user_repo.create_or_update_user(user)
        if not save_user:
            return AuthResultDTO(
                access_token=None,
                refresh_token=None,
                is_email_exists=False,
            )

        await self.user_event_producer.produce_user_registered(
            user_id=user_id,
            direction=user.direction,
            level=user.level,
        )

        access = self.token_service.create_token(user_id, "access")
        refresh = self.token_service.create_token(user_id, "refresh")

        save_refresh = await self.session_repo.save_refresh_token(refresh, user_id)
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

    @staticmethod
    def _generate_user_id() -> int:
        return uuid.uuid4().int % (2**53)
