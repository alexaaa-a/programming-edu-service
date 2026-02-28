from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from user_service.app.application.interfaces.register.token_service import TokenServiceInterface
from user_service.app.application.use_case.users import (ChangePasswordUseCase, UpdateProfileUseCase,
                                                         GetCurrentUserUseCase)
from user_service.app.presentation.api.deps import get_current_user_id_or_401
from user_service.app.presentation.api.v1.user.schema import ChangePasswordBody, UpdateProfileBody, UserShow


router = APIRouter(route_class=DishkaRoute)


@router.patch(
    "/me",
    status_code=status.HTTP_200_OK,
    description="Частичное обновление профиля. Требуется access-токен.",
)
async def patch_me(
    request: Request,
    body: UpdateProfileBody,
    token_service: FromDishka[TokenServiceInterface],
    uc: FromDishka[UpdateProfileUseCase],
) -> None:
    user_id = get_current_user_id_or_401(request, token_service)
    result = await uc(
        user_id,
        name=body.name,
        surname=body.surname,
        username=body.username,
        email=body.email,
        direction=body.direction,
        level=body.level,
    )
    if result == "email_taken":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Эта почта уже занята",
        )


@router.patch(
    "/me/password",
    status_code=status.HTTP_200_OK,
    description="Смена пароля. Требуется access-токен и текущий пароль.",
)
async def change_password(
    request: Request,
    body: ChangePasswordBody,
    token_service: FromDishka[TokenServiceInterface],
    uc: FromDishka[ChangePasswordUseCase],
) -> None:
    user_id = get_current_user_id_or_401(request, token_service)
    result = await uc(
        user_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    if result == "wrong_password":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный текущий пароль",
        )
    if result == "user_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    response_model=UserShow,
    description="Получение профиля текущего пользователя. Требуется access-токен",
)
async def get_me(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetCurrentUserUseCase],
) -> UserShow:
    user_id = get_current_user_id_or_401(request, token_service)
    curr_user = await uc(user_id)

    if curr_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден",
        )

    return UserShow(
        username=curr_user.username,
        name=curr_user.name,
        surname=curr_user.surname,
        email=curr_user.email,
        direction=curr_user.direction,
        level=curr_user.level,
    )
