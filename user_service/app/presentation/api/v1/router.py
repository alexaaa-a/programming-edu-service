from fastapi import APIRouter

from .auth.router import router as auth_router
from .user.router import router as user_router


router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(user_router, prefix="/users", tags=["users"])
