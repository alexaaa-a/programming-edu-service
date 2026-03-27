from typing import Any, Protocol


class ChatAgentProtocol(Protocol):
    async def run(
        self,
        message: str,
        chat_history: list[Any],
        context: Any,
    ) -> str:
        ...


class ChatOrchestrator:
    def __init__(self, chat_agent: ChatAgentProtocol) -> None:
        self._chat_agent = chat_agent

    async def run(
        self,
        message: str,
        chat_history: list[Any],
        user_context: Any,
    ) -> str:
        return await self._chat_agent.run(
            message=message,
            chat_history=chat_history,
            context=user_context,
        )
