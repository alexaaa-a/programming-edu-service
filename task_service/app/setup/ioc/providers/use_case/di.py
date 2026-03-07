from dishka import provide_all, Provider, Scope

from task_service.app.application.use_case.tasks.update_task_status import UpdateTaskStatusUseCase
from task_service.app.application.use_case.tasks.get_board import GetBoardUseCase
from task_service.app.application.use_case.well_known.healthcheck import HealthCheckUseCase
from task_service.app.application.use_case.sprint.get_current_sprint import GetCurrentSprintUseCase
from task_service.app.application.use_case.sprint.complete_sprint import CompleteSprintUseCase
from task_service.app.application.use_case.project.get_project_templates import GetProjectTemplatesUseCase
from task_service.app.application.use_case.project.start_project import StartProjectUseCase
from task_service.app.application.use_case.project.get_template_for_start import GetTemplateForStartUseCase
from task_service.app.application.use_case.project.create_project_template import CreateProjectTemplateUseCase


class UseCaseProvider(Provider):
    scope = Scope.REQUEST

    interactors = provide_all(
        UpdateTaskStatusUseCase,
        GetProjectTemplatesUseCase,
        GetBoardUseCase,
        GetCurrentSprintUseCase,
        CompleteSprintUseCase,
        HealthCheckUseCase,
        StartProjectUseCase,
        GetTemplateForStartUseCase,
        CreateProjectTemplateUseCase,
    )
