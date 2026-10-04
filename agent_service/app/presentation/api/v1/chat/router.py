from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request, status

from agent_service.app.application.use_cases import ChatWithTeamUseCase
from agent_service.app.application.use_cases.get_chat_history import GetChatHistoryUseCase
from agent_service.app.application.use_cases.proactive_nudge import ProactiveNudgeUseCase
from agent_service.app.config import Settings
from agent_service.app.presentation.api.deps import get_current_user_id_or_401
from agent_service.app.presentation.api.v1.chat.schema import (
    ChatHistoryMessage,
    ChatNudgeRequest,
    ChatNudgeResponse,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
)

router = APIRouter(route_class=DishkaRoute)


@router.get(
    "/chat/history",
    status_code=status.HTTP_200_OK,
    response_model=ChatHistoryResponse,
    description="Полная переписка с командой для текущего пользователя",
)
async def chat_history(
        request: Request,
        uc: FromDishka[GetChatHistoryUseCase],
        settings: FromDishka[Settings],
        task_id: int | None = None,
) -> ChatHistoryResponse:
    user_id = get_current_user_id_or_401(request, settings)
    rows = await uc(user_id=user_id, task_id=task_id)
    return ChatHistoryResponse(
        messages=[ChatHistoryMessage.model_validate(row) for row in rows],
    )


@router.post(
    "/chat",
    status_code=status.HTTP_200_OK,
    response_model=ChatResponse,
    description="Задать вопрос в чате агентной команды",
)
async def chat(
        request: Request,
        body: ChatRequest,
        uc: FromDishka[ChatWithTeamUseCase],
        settings: FromDishka[Settings],
) -> ChatResponse:
    user_id = get_current_user_id_or_401(request, settings)
    result = await uc(
        message=body.message,
        session_id=body.session_id,
        task_title=body.task_title,
        task_description=body.task_description,
        task_id=body.task_id,
        authorization=request.headers.get("Authorization") or "",
        user_id=user_id,
        turn_id=body.turn_id,
        solo_only=body.solo_only,
        emma_briefing=body.emma_briefing,
    )
    return ChatResponse(
        session_id=result.session_id,
        answer=result.answer,
        speaker=result.speaker_name,
        role=result.speaker_role,
        mode=result.mode,
        advisors=list(result.advisors),
        agent_path=[
            {
                "kind": step.kind,
                "name": step.name,
                "status": step.status,
                "detail": step.detail,
            }
            for step in result.agent_path
        ],
    )


@router.post(
    "/chat/nudge",
    status_code=status.HTTP_200_OK,
    response_model=ChatNudgeResponse,
    description="Проверить, не пора ли команде написать студенту первой",
)
async def chat_nudge(
        request: Request,
        body: ChatNudgeRequest,
        uc: FromDishka[ProactiveNudgeUseCase],
        settings: FromDishka[Settings],
) -> ChatNudgeResponse:
    user_id = get_current_user_id_or_401(request, settings)
    result = await uc(
        user_id=user_id,
        authorization=request.headers.get("Authorization") or "",
        session_id=body.session_id,
        task_title=body.task_title,
    )
    return ChatNudgeResponse(
        sent=result.sent,
        message=result.message,
        speaker_id=result.speaker_id,
        speaker_name=result.speaker_name,
        speaker_role=result.speaker_role,
        kind=result.kind,
        task_id=result.task_id,
    )
