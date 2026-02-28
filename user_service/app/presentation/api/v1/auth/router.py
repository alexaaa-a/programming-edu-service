from fastapi import APIRouter, status, HTTPException
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from user_service.app.application.use_case.authorization.login import LoginUseCase
from user_service.app.application.use_case.authorization.logout import LogoutUseCase
from user_service.app.application.use_case.authorization.refresh import RefreshUseCase
from user_service.app.presentation.api.v1.auth.schema import (
    AuthResult,
    UserRegister,
    UserLogin,
    RefreshTokenBody,
)
from user_service.app.application.use_case.authorization.register import RegisterUseCase
from user_service.app.application.dto import UserRegisterDTO, UserLoginDTO


router = APIRouter(route_class=DishkaRoute)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthResult,
    description="Регистрация для новых пользователей"
)
async def register(
        user_register: UserRegister,
        uc: FromDishka[RegisterUseCase]
) -> AuthResult:
    data = UserRegisterDTO(
        name=user_register.name,
        surname=user_register.surname,
        email=user_register.email,
        password=user_register.password,
        username=user_register.username,
    )
    tokens = await uc(data)
    if tokens.is_email_exists:
        raise HTTPException(status_code=400, detail="Пользователь с такой почтой уже существует")

    if not tokens.access_token:
        raise HTTPException(status_code=401, detail="Ошибка регистрации. Попробуйте еще раз")

    return AuthResult(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=AuthResult,
    description="Вход на платформу"
)
async def login(
        user_login: UserLogin,
        uc: FromDishka[LoginUseCase]
) -> AuthResult:
    data = UserLoginDTO(
        email=user_login.email,
        password=user_login.password
    )
    tokens = await uc(data)

    if not tokens.access_token:
        raise HTTPException(status_code=401, detail="Введен неверный логин или пароль")

    return AuthResult(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    description="Выход с платформы"
)
async def logout(
        body: RefreshTokenBody,
        uc: FromDishka[LogoutUseCase]
) -> None:
    result_logout = await uc(body.refresh_token)

    if not result_logout:
        raise HTTPException(status_code=400, detail="Не удалось выйти из системы. Попробуйте снова")


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=AuthResult,
    description="Получение нового access токена по refresh токену"
)
async def refresh(
        body: RefreshTokenBody,
        uc: FromDishka[RefreshUseCase]
) -> AuthResult:
    result_refresh = await uc(body.refresh_token)

    if not result_refresh.access_token:
        raise HTTPException(status_code=401, detail="Ошибка. Войдите снова")

    return AuthResult(
        access_token=result_refresh.access_token,
        refresh_token=result_refresh.refresh_token or body.refresh_token,
    )
