from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, status
from dishka.integrations.fastapi import DishkaRoute, FromDishka

from task_service.app.application.career import CareerState
from task_service.app.application.interfaces.services.token_service import TokenServiceInterface
from task_service.app.application.use_case.career.get_career import GetCareerUseCase
from task_service.app.application.use_case.career.spend_bonus import SpendBonusUseCase
from task_service.app.application.use_case.sprint.complete_sprint import CompleteSprintUseCase
from task_service.app.presentation.api.deps import get_current_user_id_or_401
from task_service.app.application.quests import BADGE_BY_ID, BADGES, badge_payload, quests
from task_service.app.presentation.api.v1.career.schema import (
    CareerBadgeOut,
    CareerLetterOut,
    CareerOut,
    CareerProgressOut,
    CareerPurchaseOut,
    CareerQuestOut,
    FridayDemoIn,
    FridayDemoOut,
    SpendBonusIn,
)

router = APIRouter(route_class=DishkaRoute)


def _letter_out(letter) -> CareerLetterOut:
    return CareerLetterOut(
        at=letter.at,
        old_salary=letter.old_salary,
        new_salary=letter.new_salary,
        bonus_paid=letter.bonus_paid,
        facts=list(letter.facts),
        text=letter.text,
        kind=letter.kind,
        old_grade=letter.old_grade,
        new_grade=letter.new_grade,
    )


def _to_out(state: CareerState) -> CareerOut:
    return CareerOut(
        grade=state.grade,
        salary=state.salary,
        bonus=state.bonus,
        equity=state.equity,
        raise_blocked=state.raise_blocked,
        incident_used=state.incident_used,
        appeal_used=state.appeal_used,
        letters=[_letter_out(letter) for letter in state.letters],
        pending_letter=_letter_out(state.pending_letter) if state.pending_letter else None,
        pending_forced=state.pending_forced,
        pending_demo=(
            FridayDemoOut(
                sara_line=state.pending_demo.sara_line,
                question=state.pending_demo.question,
                criterion=state.pending_demo.criterion,
            )
            if state.pending_demo
            else None
        ),
        purchases=[
            CareerPurchaseOut(
                item=purchase.item,
                price=purchase.price,
                at=purchase.at,
                task_id=purchase.task_id,
                used=purchase.used,
            )
            for purchase in state.purchases
        ],
        progress=CareerProgressOut(**asdict(state.progress)),
        badges=[
            CareerBadgeOut(
                id=badge.id,
                title=BADGE_BY_ID[badge.id].title,
                hint=BADGE_BY_ID[badge.id].hint,
                at=badge.at,
            )
            for badge in state.badges
            if badge.id in BADGE_BY_ID
        ],
        quests=[
            CareerQuestOut(
                id=quest.id,
                title=quest.title,
                hint=quest.hint,
                current=quest.current,
                target=quest.target,
                left=quest.left,
            )
            for quest in quests(state.progress, state.badges, limit=len(BADGES))
        ],
        badge_total=len(BADGES),
    )


@router.get("/career", response_model=CareerOut)
async def get_career(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[GetCareerUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    result = await uc(user_id)
    if result.error == "not_found" or result.state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карьера ещё не начата")
    return _to_out(result.state)


@router.post("/career/spend", response_model=CareerOut)
async def spend_bonus(
        request: Request,
        body: SpendBonusIn,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[SpendBonusUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    result = await uc(user_id, body.item, task_id=body.task_id)
    if result.error == "not_found" or (result.state is None and result.error == "not_found"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карьера ещё не начата")
    if result.error == "unknown_item":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестная покупка")
    if result.error == "insufficient_bonus":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Премии не хватает")
    if result.error == "needs_task":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Покупка привязана к задаче")
    if result.error == "already_bought":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Это уже куплено")
    if result.error == "not_needed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="На этом грейде критерии и так открыты")
    if result.state is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось списать премию")
    return _to_out(result.state)


@router.post("/career/consume", response_model=CareerOut)
async def consume_emma(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[SpendBonusUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    result = await uc.consume_emma(user_id)
    if result.error == "not_found" or result.state is None and result.error == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Карьера ещё не начата")
    if result.error == "nothing_to_use":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Сессии Эммы нет")
    if result.state is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось закрыть сессию")
    return _to_out(result.state)


@router.post("/career/demo")
async def submit_friday_demo(
        request: Request,
        body: FridayDemoIn,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[CompleteSprintUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    result = await uc.submit_demo(
        user_id,
        pitch=body.pitch,
        answer=body.answer,
    )
    if result.error == "empty":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message or "Напиши питч и ответ")
    if result.error == "no_demo":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.message or "Пятничного демо нет")
    if result.error == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message or "Не найдено")
    if result.error == "tasks_open":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message or "Не все задачи спринта выполнены",
        )
    if result.error == "unread":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.message or "Сара не дочитала ответ",
        )
    if not result.ok or result.letter is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message or "Не удалось сохранить письмо",
        )
    return {
        "status": "letter",
        "letter": _letter_out(result.letter).model_dump(mode="json"),
        "unlocked": badge_payload(result.unlocked),
    }


@router.post("/career/accept")
async def accept_letter_route(
        request: Request,
        token_service: FromDishka[TokenServiceInterface],
        uc: FromDishka[CompleteSprintUseCase],
):
    user_id = get_current_user_id_or_401(request=request, token_service=token_service)
    authorization = request.headers.get("Authorization") or ""
    result = await uc.accept(user_id, authorization=authorization)
    if result.error == "no_letter":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.message or "Письма нет")
    if result.error == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.message or "Не найдено")
    if result.error == "tasks_open":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message or "Не все задачи спринта выполнены")
    if result.error == "empty_next_sprint":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message or "Шаблон следующего спринта без задач")
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.message or "Не удалось открыть следующий спринт")
    return {
        "status": result.status,
        "forced": result.forced,
        "unlocked": badge_payload(result.unlocked),
    }
