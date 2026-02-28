from dishka.integrations.fastapi import FromDishka, DishkaRoute
from fastapi import APIRouter, status

from user_service.app.application.use_case.well_known.health import HealthUseCase


router = APIRouter(route_class=DishkaRoute)


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    description="Liveness probe - проверяет что приложение живое"
)
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    description="Readiness probe - проверяет готовность принимать трафик"
)
async def readiness(
        uc: FromDishka[HealthUseCase]
) -> dict[str, str]:
    await uc()
    return {"status": "ready"}


@router.get(
    "/startup",
    status_code=status.HTTP_200_OK,
    description="Kubernetes startup probe - проверяет готовность при старте"
)
async def startup(
        uc: FromDishka[HealthUseCase]
) -> dict[str, str]:
    await uc()
    return {"status": "started"}
