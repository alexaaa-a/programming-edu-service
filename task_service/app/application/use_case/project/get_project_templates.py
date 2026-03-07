from task_service.app.application.dto.project import ProjectTemplateDTO
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.application.interfaces.db.user_project_db import UserProjectDBInterface
from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface


class GetProjectTemplatesUseCase:
    def __init__(
            self,
            project_db: ProjectDBInterface,
            user_project_db: UserProjectDBInterface,
            meta_user_db: MetaUserDBInterface
    ) -> None:
        self.project_db = project_db
        self.user_project_db = user_project_db
        self.meta_user_db = meta_user_db

    async def __call__(self, user_id: int) -> list[ProjectTemplateDTO] | None:
        user_projects = await self.user_project_db.get_all_user_projects(user_id)
        if not user_projects:
            exclude_ids = []
        else:
            exclude_ids = [s.template_id for s in user_projects]

        meta_user = await self.meta_user_db.get_meta_user(user_id)
        if not meta_user:
            return None

        return await self.project_db.get_all_templates_for_user(
            exclude_ids, meta_user.level, meta_user.direction
        )
