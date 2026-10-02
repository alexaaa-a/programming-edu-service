from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from task_service.app.application.career import appeal_available
from task_service.app.application.interfaces.admin_role_gateway import (
    AdminRoleGatewayInterface,
)
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.application.interfaces.services.token_service import (
    TokenServiceInterface,
)
from task_service.app.application.use_case.sprint.complete_sprint import (
    CompleteSprintUseCase,
)
from task_service.app.application.use_case.sprint.get_current_sprint import (
    GetCurrentSprintUseCase,
)
from task_service.app.infrastructure.http.admin_role import can_force_sprint
from task_service.app.presentation.api.deps import get_current_user_id_or_401
from task_service.app.application.quests import badge_payload
from task_service.app.presentation.api.v1.career.router import _letter_out
from task_service.app.presentation.api.v1.sprint.schema import Sprint

router = APIRouter(route_class=DishkaRoute)

_FORCE_CONFIRM_HEADER = "X-Confirm-Force-Sprint"
_FORCE_CONFIRM_VALUES = {"1", "true", "yes"}


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
        close_mode=getattr(curr_sprint, "close_mode", None),
    )


@router.post(
    "/sprint/complete",
    status_code=status.HTTP_200_OK,
    description="Завершение текущего спринта пользователя",
)
async def complete_sprint(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        admin_roles: FromDishka[AdminRoleGatewayInterface],
        career_db: FromDishka[CareerDBInterface],
        uc: FromDishka[CompleteSprintUseCase],
        force: bool = False,
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    authorization = request.headers.get("Authorization") or ""
    role = await admin_roles.get_my_role(authorization)
    force_ok = can_force_sprint(role)
    career = await career_db.get(user_id)
    appeal_ok = appeal_available(career)

    if force:
        if not force_ok and not appeal_ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Принудительное открытие доступно admin "
                    "или одной апелляцией за спринт с грейда Strong junior."
                ),
            )
        confirm = (request.headers.get(_FORCE_CONFIRM_HEADER) or "").strip().lower()
        if confirm not in _FORCE_CONFIRM_VALUES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Принудительное открытие требует подтверждения "
                    f"(заголовок {_FORCE_CONFIRM_HEADER}: true)."
                ),
            )
    complete = await uc(
        user_id,
        authorization=authorization,
        force=force,
        consume_appeal=force and not force_ok and appeal_ok,
    )

    if complete.error == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=complete.message or "Не найдено",
        )

    if complete.error == "tasks_open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=complete.message or "Не все задачи спринта выполнены",
        )

    if complete.error == "empty_next_sprint":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=complete.message or "Шаблон следующего спринта без задач",
        )

    if complete.error == "hold":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "hold",
                "message": complete.message
                or "Траектория ещё тяжёлая — рано открывать следующий спринт.",
                "weak_count": complete.weak_count,
                "task_count": complete.task_count,
                "force_allowed": force_ok or appeal_ok,
            },
        )

    if not complete.ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=complete.message or "Не удалось завершить спринт",
        )

    return _sprint_done(complete)


def _sprint_done(complete) -> dict:
    body = {"status": complete.status, "forced": complete.forced}
    if complete.unlocked:
        body["unlocked"] = badge_payload(complete.unlocked)
    if complete.letter is not None:
        body["letter"] = _letter_out(complete.letter).model_dump(mode="json")
    if complete.demo is not None:
        body["demo"] = {
            "sara_line": complete.demo.sara_line,
            "question": complete.demo.question,
            "criterion": complete.demo.criterion,
        }
    return body
