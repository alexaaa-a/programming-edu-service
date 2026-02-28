from pydantic import BaseModel, EmailStr, Field


class AuthResult(BaseModel):
    access_token: str
    refresh_token: str


class UserRegister(BaseModel):
    username: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=2, max_length=30)
    surname: str = Field(min_length=2, max_length=30)
    email: EmailStr


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshTokenBody(BaseModel):
    refresh_token: str = Field(min_length=1)
