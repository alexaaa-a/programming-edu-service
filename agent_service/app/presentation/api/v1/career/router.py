import hmac
import logging

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent_service.app.application.career_puzzle import CareerPuzzleUseCase
from agent_service.app.config import Settings

_logger = logging.getLogger("agent_service.career_puzzle")

router = APIRouter(route_class=DishkaRoute)


class SnippetOut(BaseModel):
    code: str
    bug: str


class IncidentOut(BaseModel):
    scene: str
    code: str
    expect: str


class GradeIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)
    bug: str = Field(min_length=1, max_length=500)
    note: str = Field(min_length=1, max_length=2000)


class GradeOut(BaseModel):
    found: bool
    emma: str


class DemoIn(BaseModel):
    criterion: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)


class DemoOut(BaseModel):
    addresses: bool


def _authorize(request: Request, settings: Settings) -> None:
    expected = settings.career_settings.token.strip()
    given = request.headers.get("X-Career-Token") or ""
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Нет доступа")


@router.post("/career/peer-snippet", response_model=SnippetOut)
async def peer_snippet(
        request: Request,
        uc: FromDishka[CareerPuzzleUseCase],
        settings: FromDishka[Settings],
) -> SnippetOut:
    _authorize(request, settings)
    try:
        snippet = await uc.generate_snippet()
    except Exception:
        _logger.exception("career snippet failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Модель не собрала код")
    return SnippetOut(code=snippet.code, bug=snippet.bug)


@router.post("/career/night-incident", response_model=IncidentOut)
async def night_incident(
        request: Request,
        uc: FromDishka[CareerPuzzleUseCase],
        settings: FromDishka[Settings],
) -> IncidentOut:
    _authorize(request, settings)
    try:
        drafted = await uc.generate_incident()
    except Exception:
        _logger.exception("career incident failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Модель не собрала инцидент")
    return IncidentOut(scene=drafted.scene, code=drafted.code, expect=drafted.expect)


@router.post("/career/peer-grade", response_model=GradeOut)
async def peer_grade(
        request: Request,
        body: GradeIn,
        uc: FromDishka[CareerPuzzleUseCase],
        settings: FromDishka[Settings],
) -> GradeOut:
    _authorize(request, settings)
    try:
        graded = await uc.grade_note(body.code, body.bug, body.note)
    except Exception:
        _logger.exception("career grade failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Модель не прочитала заметку")
    return GradeOut(found=graded.found, emma=graded.emma)


@router.post("/career/demo-grade", response_model=DemoOut)
async def demo_grade(
        request: Request,
        body: DemoIn,
        uc: FromDishka[CareerPuzzleUseCase],
        settings: FromDishka[Settings],
) -> DemoOut:
    _authorize(request, settings)
    try:
        addresses = await uc.grade_demo(body.criterion, body.answer)
    except Exception:
        _logger.exception("career demo grade failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Модель не прочитала ответ")
    return DemoOut(addresses=addresses)
