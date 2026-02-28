from pydantic import BaseModel, EmailStr, Field


class ChangePasswordBody(BaseModel):
    current_password: str = Field(..., min_length=1, description="Текущий пароль")
    new_password: str = Field(..., min_length=8, max_length=64, description="Новый пароль")


class UpdateProfileBody(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=30, description="Имя")
    surname: str | None = Field(None, min_length=2, max_length=30, description="Фамилия")
    username: str | None = Field(None, min_length=2, max_length=30, description="Юзернейм")
    email: EmailStr | None = Field(None, description="Почта")
    direction: str | None = Field(None, min_length=1, max_length=100, description="Направление")
    level: str | None = Field(None, min_length=1, max_length=100, description="Уровень")


class UserShow(BaseModel):
    username: str
    name: str
    surname: str
    level: str | None
    direction: str | None
    email: str
