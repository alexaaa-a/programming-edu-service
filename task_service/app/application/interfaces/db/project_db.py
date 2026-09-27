from abc import abstractmethod
from typing import Protocol

from task_service.app.application.dto.project import ProjectTemplateDTO


class ProjectDBInterface(Protocol):
    @abstractmethod
    async def get_all_templates_for_user(
            self,
            exclude_ids: list[int],
            level: str,
            direction: str
    ) -> list[ProjectTemplateDTO] | None:
        raise NotImplementedError

    @abstractmethod
    async def get_template_by_id(self, template_id: str) -> ProjectTemplateDTO | None:
        raise NotImplementedError

    @abstractmethod
    async def create_template(self, template: ProjectTemplateDTO) -> bool:
        raise NotImplementedError
