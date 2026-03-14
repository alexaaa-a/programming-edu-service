from fastapi import APIRouter

from .submissions.router import router as submissions_router
from .tasks.router import router as tasks_router


router = APIRouter()

router.include_router(submissions_router, tags=["submissions"])
router.include_router(tasks_router, tags=["tasks"])
