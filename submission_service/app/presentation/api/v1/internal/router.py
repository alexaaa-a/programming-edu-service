import hmac
import logging

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from submission_service.app.application.drills.bank import DRILL_BY_ID
from submission_service.app.application.interfaces.db.task_cache import TaskCacheInterface
from submission_service.app.application.use_case.drills.record_drill_run import (
    RecordDrillRunUseCase,
)
from submission_service.app.application.use_case.submissions.get_review_agreement import (
    GetReviewAgreementUseCase,
)
from submission_service.app.config import Settings

_logger = logging.getLogger("submission_service.internal")

router = APIRouter(route_class=DishkaRoute)

HEADER = "X-Internal-Token"


class TaskTests(BaseModel):
    task_id: int
    user_id: int
    tests: str


def _authorize(request: Request, settings: Settings) -> None:
    expected = settings.internal_settings.token.strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Внутренний доступ не настроен",
        )
    given = request.headers.get(HEADER) or ""
    if not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Нет доступа")


@router.get(
    "/internal/tasks/{task_id}/tests",
    response_model=TaskTests,
    description="Скрытые тесты задачи для прогона в песочнице (сервис-сервис)",
)
async def task_tests(
        request: Request,
        task_id: int,
        user_id: int,
        task_cache: FromDishka[TaskCacheInterface],
        settings: FromDishka[Settings],
) -> TaskTests:
    _authorize(request, settings)
    getter = getattr(task_cache, "get_task_tests", None)
    tests = await getter(task_id, user_id) if getter is not None else None
    if not tests:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="У задачи нет тестов",
        )
    return TaskTests(task_id=task_id, user_id=user_id, tests=tests)


class ReviewAgreement(BaseModel):
    total: int
    used: int
    agreement: float
    kappa: float
    false_pass: int
    false_fail: int
    false_pass_rate: float
    false_fail_rate: float
    both_pass: int
    both_fail: int
    score_gap: float


@router.get(
    "/internal/review-agreement",
    response_model=ReviewAgreement,
    description="Совпадение оценки команды с тестами задачи по проверенным сдачам",
)
async def review_agreement(
        request: Request,
        uc: FromDishka[GetReviewAgreementUseCase],
        settings: FromDishka[Settings],
        limit: int = 1000,
) -> ReviewAgreement:
    _authorize(request, settings)
    report = await uc(limit=limit)
    _logger.info(
        "eval.review_agreement used=%s agreement=%.4f kappa=%.4f",
        report.used,
        report.agreement,
        report.kappa,
    )
    return ReviewAgreement(**report.as_dict())


class DrillTests(BaseModel):
    drill_id: str
    skill_id: str
    tests: str


class DrillResultIn(BaseModel):
    user_id: int
    passed: int
    total: int


class DrillResultOut(BaseModel):
    stored: bool
    skill_id: str = ""
    passed: int = 0
    total: int = 0


@router.get(
    "/internal/drills/{drill_id}",
    response_model=DrillTests,
    description="Тесты упражнения для прогона в песочнице (сервис-сервис)",
)
async def drill_tests(
        request: Request,
        drill_id: str,
        settings: FromDishka[Settings],
) -> DrillTests:
    _authorize(request, settings)
    drill = DRILL_BY_ID.get(drill_id)
    if drill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Упражнение не найдено")
    return DrillTests(drill_id=drill.id, skill_id=drill.skill_id, tests=drill.tests)


@router.post(
    "/internal/drills/{drill_id}/result",
    response_model=DrillResultOut,
    description="Результат прогона упражнения: идёт в модель знаний (сервис-сервис)",
)
async def drill_result(
        request: Request,
        drill_id: str,
        body: DrillResultIn,
        uc: FromDishka[RecordDrillRunUseCase],
        settings: FromDishka[Settings],
) -> DrillResultOut:
    _authorize(request, settings)
    result = await uc(
        user_id=body.user_id,
        drill_id=drill_id,
        passed=body.passed,
        total=body.total,
    )
    if result.error == "unknown_drill":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Упражнение не найдено")
    if result.error == "empty_run":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой прогон")
    run = result.run
    _logger.info(
        "drill.run user_id=%s drill=%s passed=%s/%s stored=%s",
        body.user_id,
        drill_id,
        run.passed if run else 0,
        run.total if run else 0,
        result.stored,
    )
    return DrillResultOut(
        stored=result.stored,
        skill_id=run.skill_id if run else "",
        passed=run.passed if run else 0,
        total=run.total if run else 0,
    )
