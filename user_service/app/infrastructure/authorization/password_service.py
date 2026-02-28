from passlib.context import CryptContext

from user_service.app.application.interfaces.register.password_service import (
    PasswordServiceInterface,
)


class PasswordService(PasswordServiceInterface):
    def __init__(self) -> None:
        self._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        return self._pwd_context.hash(password)

    def verify_password(self, password: str, hashed_password: str) -> bool:
        return self._pwd_context.verify(password, hashed_password)
