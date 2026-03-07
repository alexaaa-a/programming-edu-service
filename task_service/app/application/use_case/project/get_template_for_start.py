import random

from task_service.app.application.interfaces.db.meta_user_db import MetaUserDBInterface
from task_service.app.application.interfaces.db.project_db import ProjectDBInterface
from task_service.app.application.interfaces.db.user_project_db import UserProjectDBInterface


class GetTemplateForStartUseCase:
    def __init__(
            self,
            meta_user_db: MetaUserDBInterface,
            project_db: ProjectDBInterface,
            user_project_db: UserProjectDBInterface
    ) -> None:
        self.meta_user_db = meta_user_db
        self.project_db = project_db
        self.user_project_db = user_project_db

    async def __call__(self, user_id: int) -> int | None:
        data_user = await self.meta_user_db.get_meta_user(user_id)

        if data_user is None:
            return None

        user_projects = await self.user_project_db.get_all_user_projects(user_id)
        if not user_projects:
            exclude_ids = []
        else:
            exclude_ids = [s.template_id for s in user_projects]

        templates = await self.project_db.get_all_templates_for_user(
            exclude_ids,
            data_user.level,
            data_user.direction
        )

        if not templates:
            return None

        random_template = random.choice(templates)
        return random_template.project_template_id if random_template else None
