from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, status

from agent_service.app.application.use_cases import ChatWithTeamUseCase
from agent_service.app.presentation.api.v1.chat.schema import (
    ChatRequest,
    ChatResponse,
)

router = APIRouter(route_class=DishkaRoute)


@router.post(
    "/chat",
    status_code=status.HTTP_200_OK,
    response_model=ChatResponse,
    description="Задать вопрос в чате агентной команды",
)
async def chat(
    body: ChatRequest,
    uc: FromDishka[ChatWithTeamUseCase],
) -> ChatResponse:
    result = await uc(message=body.message, session_id=body.session_id)
    return ChatResponse(session_id=result.session_id, answer=result.answer)
