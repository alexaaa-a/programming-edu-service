from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import FromDishka, DishkaRoute

from task_service.app.application.dto.project import (
    ProjectTemplateDTO,
    SprintOrderDTO,
    TaskDTO as TemplateTaskDTO,
)
from task_service.app.application.interfaces.admin_role_gateway import (
    AdminRoleGatewayInterface,
)
from task_service.app.application.interfaces.services.token_service import (
    TokenServiceInterface,
)
from task_service.app.application.use_case.project.start_project import StartProjectUseCase
from task_service.app.application.use_case.project.get_project_templates import GetProjectTemplatesUseCase
from task_service.app.application.use_case.project.create_project_template import CreateProjectTemplateUseCase
from task_service.app.application.use_case.project.get_template_for_start import GetTemplateForStartUseCase
from task_service.app.infrastructure.http.admin_role import can_force_sprint
from task_service.app.presentation.api.deps import get_current_user_id_or_401
from task_service.app.presentation.api.v1.project.schema import StartProject, ProjectTemplate, Task, SprintOrder


router = APIRouter(route_class=DishkaRoute)


@router.post(
    "/project/start",
    status_code=status.HTTP_201_CREATED,
    description="Старт нового проекта пользователя"
)
async def start_project(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[StartProjectUseCase],
        body: StartProject
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    new_project = await uc(user_id, body.template_id)

    if new_project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="У пользователя уже есть активный проект или шаблон не найден",
        )

    if not new_project:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка создания проекта",
        )

    return {"status": "created"}


@router.get(
    "/project/templates",
    status_code=status.HTTP_200_OK,
    response_model=list[ProjectTemplate],
    description="Получение всех шаблонов проектов, подходящих пользователю",
)
async def get_project_templates(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetProjectTemplatesUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    templates = await uc(user_id)

    if templates is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь или шаблоны не найдены",
        )

    return [
        ProjectTemplate(
            project_template_id=t.project_template_id,
            title=t.title,
            description=t.description,
            sprints=[
                SprintOrder(
                    order=s.order,
                    title=s.title,
                    tasks=[Task(title=task.title, description=task.description) for task in s.tasks],
                )
                for s in t.sprints
            ],
            direction=t.direction,
            level=t.level,
        )
        for t in templates
    ]


@router.get(
    "/project/template-for-start",
    status_code=status.HTTP_200_OK,
    description="Получение случайного шаблона для старта нового проекта",
)
async def get_template_for_start(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetTemplateForStartUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    template_id = await uc(user_id)

    if template_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден или нет подходящих шаблонов",
        )

    return {"template_id": template_id}


@router.post(
    "/project/template",
    status_code=status.HTTP_201_CREATED,
    description="Создание шаблона проекта (admin/superadmin)",
)
async def create_project_template(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        admin_roles: FromDishka[AdminRoleGatewayInterface],
        uc: FromDishka[CreateProjectTemplateUseCase],
        body: ProjectTemplate,
):
    get_current_user_id_or_401(request=request, token_service=token_service)
    authorization = request.headers.get("Authorization") or ""
    role = await admin_roles.get_my_role(authorization)
    if not can_force_sprint(role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создание шаблонов доступно только admin/superadmin.",
        )

    dto = ProjectTemplateDTO(
        project_template_id=None,
        title=body.title,
        description=body.description,
        sprints=[
            SprintOrderDTO(
                order=s.order,
                title=s.title,
                tasks=[
                    TemplateTaskDTO(title=t.title, description=t.description, tests=t.tests)
                    for t in s.tasks
                ],
            )
            for s in body.sprints
        ],
        direction=body.direction,
        level=body.level,
    )
    created = await uc(dto)

    if not created:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать шаблон",
        )

    return {"status": "created"}
