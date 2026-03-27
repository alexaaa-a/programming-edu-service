from agent_service.app.application.orchestrators.chat_orchestrator import ChatOrchestrator
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.dto.chat import ChatWithTeamResult


class ChatWithTeamUseCase:
    def __init__(
        self,
        orchestrator: ChatOrchestrator,
        memory: MemoryInterface,
    ) -> None:
        self._orchestrator = orchestrator
        self._memory = memory

    async def __call__(
        self,
        message: str,
        session_id: str,
    ) -> ChatWithTeamResult:
        user_context = {"session_id": session_id}

        answer = await self._orchestrator.run(
            message=message,
            chat_history=[],
            user_context=user_context,
        )

        return ChatWithTeamResult(session_id=session_id, answer=answer)
