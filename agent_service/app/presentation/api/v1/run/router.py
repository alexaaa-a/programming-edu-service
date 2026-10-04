from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent_service.app.application.use_cases.run_drill import RunDrillUseCase
from agent_service.app.application.use_cases.run_task_tests import RunTaskTestsUseCase
from agent_service.app.config import Settings
from agent_service.app.presentation.api.deps import get_current_user_id_or_401

router = APIRouter(route_class=DishkaRoute)


class RunTestsRequest(BaseModel):
    task_id: int
    code: str = Field(min_length=1, max_length=40_000)


class FailedTest(BaseModel):
    name: str
    message: str = ""


class RunTestsResponse(BaseModel):
    status: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    failures: list[FailedTest] = Field(default_factory=list)
    detail: str = ""


@router.post(
    "/run-tests",
    status_code=status.HTTP_200_OK,
    response_model=RunTestsResponse,
    description="Прогнать тесты задачи по текущему коду. Попытку не тратит.",
)
async def run_tests(
        request: Request,
        body: RunTestsRequest,
        uc: FromDishka[RunTaskTestsUseCase],
        settings: FromDishka[Settings],
) -> RunTestsResponse:
    user_id = get_current_user_id_or_401(request, settings)
    result = await uc(task_id=body.task_id, code=body.code, user_id=user_id)

    if result.error == "busy":
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.message or "Прогон уже идёт",
        )
    if result.error == "no_tests":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message or "У задачи нет тестов",
        )
    if result.error in {"empty", "too_long", "unsupported"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message or "Прогон невозможен",
        )
    if result.error == "unavailable" or result.run is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.message or "Прогон тестов недоступен",
        )

    run = result.run
    return RunTestsResponse(
        status=run.status,
        total=run.total,
        passed=run.passed,
        failed=run.failed,
        failures=[
            FailedTest(name=case.name, message=case.message)
            for case in run.cases
            if not case.passed
        ],
        detail=run.detail,
    )


class RunDrillRequest(BaseModel):
    drill_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=20_000)


class RunDrillResponse(RunTestsResponse):
    skill_id: str = ""
    recorded: bool = False


@router.post(
    "/run-drill",
    status_code=status.HTTP_200_OK,
    response_model=RunDrillResponse,
    description="Прогнать упражнение. Попытку не тратит, результат идёт в модель знаний.",
)
async def run_drill(
        request: Request,
        body: RunDrillRequest,
        uc: FromDishka[RunDrillUseCase],
        settings: FromDishka[Settings],
) -> RunDrillResponse:
    user_id = get_current_user_id_or_401(request, settings)
    result = await uc(drill_id=body.drill_id, code=body.code, user_id=user_id)

    if result.error == "busy":
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.message or "Прогон уже идёт",
        )
    if result.error == "no_drill":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.message or "Упражнение не найдено",
        )
    if result.error in {"empty", "too_long", "unsupported"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message or "Прогон невозможен",
        )
    if result.error == "unavailable" or result.run is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.message or "Прогон упражнений недоступен",
        )

    run = result.run
    return RunDrillResponse(
        status=run.status,
        total=run.total,
        passed=run.passed,
        failed=run.failed,
        failures=[
            FailedTest(name=case.name, message=case.message)
            for case in run.cases
            if not case.passed
        ],
        detail=run.detail,
        skill_id=result.skill_id,
        recorded=result.recorded,
    )
