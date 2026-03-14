from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from task_service.app.application.interfaces.services.token_service import (
    TokenServiceInterface,
)
from task_service.app.application.use_case.sprint.complete_sprint import (
    CompleteSprintUseCase,
)
from task_service.app.application.use_case.sprint.get_current_sprint import (
    GetCurrentSprintUseCase,
)
from task_service.app.presentation.api.deps import get_current_user_id_or_401
from task_service.app.presentation.api.v1.sprint.schema import Sprint

router = APIRouter(route_class=DishkaRoute)


@router.get(
    "/sprint/current",
    status_code=status.HTTP_200_OK,
    response_model=Sprint,
    description="Получение текущего спринта пользователя",
)
async def get_current_sprint(
    request: Request,
    token_service: FromDishka[TokenServiceInterface],
    uc: FromDishka[GetCurrentSprintUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    curr_sprint = await uc(user_id)

    if curr_sprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Спринт не найден",
        )

    return Sprint(
        sprint_id=curr_sprint.sprint_id,
        user_project_id=curr_sprint.user_project_id,
        user_id=user_id,
        order=curr_sprint.order,
        status=curr_sprint.status,
        started_at=curr_sprint.started_at,
        completed_at=curr_sprint.completed_at,
    )


@router.post(
    "/sprint/complete",
    status_code=status.HTTP_200_OK,
    description="Завершение текущего спринта пользователя",
)
async def complete_sprint(
    request: Request,
    token_service: FromDishka[TokenServiceInterface],
    uc: FromDishka[CompleteSprintUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    complete = await uc(user_id)

    if complete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Не найдено",
        )

    if complete is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не все задачи спринта выполнены",
        )

    return {"status": complete}
