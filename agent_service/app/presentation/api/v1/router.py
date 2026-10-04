from fastapi import APIRouter

from agent_service.app.presentation.api.v1.career.router import router as career_router
from agent_service.app.presentation.api.v1.chat.router import router as chat_router
from agent_service.app.presentation.api.v1.eval.router import router as eval_router
from agent_service.app.presentation.api.v1.run.router import router as run_router
from agent_service.app.presentation.api.v1.templates.router import router as templates_router

router = APIRouter()

router.include_router(chat_router, tags=["chat"])
router.include_router(eval_router, tags=["eval"])
router.include_router(career_router, tags=["career"])
router.include_router(run_router, tags=["run"])
router.include_router(templates_router, tags=["templates"])
