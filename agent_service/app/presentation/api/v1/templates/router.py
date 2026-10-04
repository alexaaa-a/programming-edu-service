import logging

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent_service.app.application.templates.models import TemplateSpec
from agent_service.app.application.use_cases.generate_project_template import (
    GenerateProjectTemplateUseCase,
)
from agent_service.app.config import Settings
from agent_service.app.infrastructure.http import HttpAdminRoleGateway, is_admin
from agent_service.app.presentation.api.deps import get_current_user_id_or_401

_logger = logging.getLogger("agent_service.templates")

router = APIRouter(route_class=DishkaRoute)


class GenerateSprintRequest(BaseModel):
    topic: str = Field(min_length=5, max_length=200)
    direction: str = "backend"
    level: str = "junior"
    sprints: int = Field(default=3, ge=1, le=5)
    tasks_per_sprint: int = Field(default=4, ge=2, le=6)
    notes: str = Field(default="", max_length=600)
    with_tests: bool = True
    order: int = Field(default=1, ge=1, le=5)
    used_titles: list[str] = Field(default_factory=list, max_length=40)


class GeneratedTask(BaseModel):
    title: str
    description: str
    tests: str = ""


class IssueOut(BaseModel):
    code: str
    message: str
    task: str = ""


class TaskReportOut(BaseModel):
    title: str
    ok: bool
    attempts: int = 1
    tests_total: int = 0
    reference_passed: int = 0
    broken_failed: int = 0
    tests_kept: bool = False
    dropped: bool = False
    issues: list[IssueOut] = Field(default_factory=list)


class GenerateSprintResponse(BaseModel):
    order: int
    sprint_title: str = ""
    project_title: str = ""
    project_description: str = ""
    tasks: list[GeneratedTask] = Field(default_factory=list)
    ok: bool = False
    rounds: int = 0
    tests_ran: bool = False
    issues: list[IssueOut] = Field(default_factory=list)
    reports: list[TaskReportOut] = Field(default_factory=list)
    summary: str = ""


@router.post(
    "/templates/sprint",
    status_code=status.HTTP_200_OK,
    response_model=GenerateSprintResponse,
    description="Собрать и проверить один спринт шаблона (admin/superadmin)",
)
async def generate_sprint(
        request: Request,
        body: GenerateSprintRequest,
        uc: FromDishka[GenerateProjectTemplateUseCase],
        roles: FromDishka[HttpAdminRoleGateway],
        settings: FromDishka[Settings],
) -> GenerateSprintResponse:
    get_current_user_id_or_401(request, settings)
    if not settings.template_settings.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Генерация шаблонов выключена",
        )
    role = await roles.get_my_role(request.headers.get("Authorization") or "")
    if not is_admin(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Генерация шаблонов доступна только admin/superadmin.",
        )

    spec = TemplateSpec(
        topic=body.topic,
        direction=body.direction,
        level=body.level,
        sprints=body.sprints,
        tasks_per_sprint=body.tasks_per_sprint,
        notes=body.notes,
        with_tests=body.with_tests,
    )
    try:
        result = await uc.generate_sprint(spec, body.order, body.used_titles)
    except Exception:
        _logger.exception("template.generate.failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Модель не ответила, попробуй ещё раз",
        )

    report = result.report
    sprint = result.sprint
    return GenerateSprintResponse(
        order=body.order,
        sprint_title=sprint.title if sprint else "",
        project_title=result.project_title,
        project_description=result.project_description,
        tasks=[
            GeneratedTask(title=task.title, description=task.description, tests=task.tests)
            for task in (sprint.tasks if sprint else [])
        ],
        ok=report.ok,
        rounds=report.rounds,
        tests_ran=report.tests_ran,
        issues=[IssueOut(**issue.as_dict()) for issue in report.issues],
        reports=[
            TaskReportOut(
                title=item.title,
                ok=item.ok,
                attempts=item.attempts,
                tests_total=item.tests_total,
                reference_passed=item.reference_passed,
                broken_failed=item.broken_failed,
                tests_kept=item.tests_kept,
                dropped=item.dropped,
                issues=[IssueOut(**issue.as_dict()) for issue in item.issues],
            )
            for item in report.tasks
        ],
        summary=report.as_text(),
    )
