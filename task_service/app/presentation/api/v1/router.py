from fastapi import APIRouter

from .career.router import router as career_router
from .project.router import router as project_router
from .sprint.router import router as sprint_router
from .tasks.router import router as tasks_router


router = APIRouter()

router.include_router(project_router, tags=["project"])
router.include_router(sprint_router, tags=["sprint"])
router.include_router(tasks_router, tags=["tasks"])
router.include_router(career_router, tags=["career"])
