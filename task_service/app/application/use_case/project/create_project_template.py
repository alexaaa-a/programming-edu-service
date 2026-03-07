import uuid

from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.application.dto.project import ProjectTemplateDTO


class CreateProjectTemplateUseCase:
    def __init__(self, project_db: ProjectDBInterface):
        self.project_db = project_db

    async def __call__(self, project_template: ProjectTemplateDTO) -> bool:
        project_template_id = self._generate_project_template_id()
        project_template.project_template_id = project_template_id

        return await self.project_db.create_template(project_template)

    @staticmethod
    def _generate_project_template_id() -> int:
        return uuid.uuid4().int % (2**53)
