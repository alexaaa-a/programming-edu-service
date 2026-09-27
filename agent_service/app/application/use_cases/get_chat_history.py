from agent_service.app.application.chat_transcript import chat_thread_id, transcript_message
from agent_service.app.application.interfaces import ChatHistoryRepository


class GetChatHistoryUseCase:
    def __init__(self, history: ChatHistoryRepository) -> None:
        self._history = history

    async def __call__(self, user_id: str, task_id: int | None = None) -> list[dict[str, str | None]]:
        thread = chat_thread_id(user_id, session_id="", task_id=task_id)
        rows = await self._history.list_history(thread)
        return [transcript_message(row) for row in rows]
