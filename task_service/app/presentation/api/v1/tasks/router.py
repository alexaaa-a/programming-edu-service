from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from task_service.app.application.interfaces.services.token_service import (
    TokenServiceInterface,
)
from task_service.app.application.use_case.tasks.get_board import GetBoardUseCase
from task_service.app.application.use_case.tasks.update_task_status import (
    UpdateTaskStatusUseCase,
)
from task_service.app.presentation.api.deps import get_current_user_id_or_401
from task_service.app.presentation.api.v1.tasks.schema import (
    BoardResponse,
    TaskResponse,
    UpdateTaskStatus,
)

router = APIRouter(route_class=DishkaRoute)


def _task_to_response(t) -> TaskResponse:
    return TaskResponse(
        task_id=t.task_id,
        user_id=t.user_id,
        user_project_id=t.user_project_id,
        sprint_id=t.sprint_id,
        title=t.title,
        description=t.description,
        status=t.status,
        created_at=t.created_at,
        completed_at=t.completed_at,
    )


@router.get(
    "/tasks/board",
    status_code=status.HTTP_200_OK,
    response_model=BoardResponse,
    description="Получение доски задач текущего спринта",
)
async def get_board(
    request: Request,
    token_service: FromDishka[TokenServiceInterface],
    uc: FromDishka[GetBoardUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    board = await uc(user_id)

    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Текущий спринт или задачи не найдены",
        )

    return BoardResponse(
        todo=[_task_to_response(t) for t in board["todo"]],
        in_progress=[_task_to_response(t) for t in board["in_progress"]],
        review=[_task_to_response(t) for t in board["review"]],
        done=[_task_to_response(t) for t in board["done"]],
    )


@router.patch(
    "/tasks/{task_id}/status",
    status_code=status.HTTP_200_OK,
    description="Обновление статуса задачи",
)
async def update_task_status(
    request: Request,
    task_id: int,
    body: UpdateTaskStatus,
    token_service: FromDishka[TokenServiceInterface],
    uc: FromDishka[UpdateTaskStatusUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    result = await uc(user_id, task_id, body.status)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задача не найдена или переход в данный статус невозможен",
        )

    if result is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый переход статуса (todo→in_progress→review→done)",
        )

    return {"status": "updated"}
