import logging

from dishka import Provider, Scope, provide

from agent_service.app.application.agents.chat_agent import ChatAgent
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.orchestrators.chat_orchestrator import (
    ChatAgentProtocol,
    ChatOrchestrator,
)
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.use_cases import ChatWithTeamUseCase
from agent_service.app.infrastructure.observability.agent_wrappers import (
    ChatAgentWithObservability,
)


class ChatAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def chat_agent(
        self,
        llm: LLMInterface,
        memory: MemoryInterface,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> ChatAgentProtocol:
        agent = ChatAgent(llm=llm, memory=memory)
        return ChatAgentWithObservability(agent, logger=logger, metrics=metrics)


class ChatOrchestratorProvider(Provider):
    @provide(scope=Scope.APP)
    def chat_orchestrator(
        self,
        chat_agent: ChatAgentProtocol,
    ) -> ChatOrchestrator:
        return ChatOrchestrator(chat_agent=chat_agent)


class ChatWithTeamUseCaseProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def chat_with_team_use_case(
        self,
        chat_orchestrator: ChatOrchestrator,
        memory: MemoryInterface,
    ) -> ChatWithTeamUseCase:
        return ChatWithTeamUseCase(
            orchestrator=chat_orchestrator,
            memory=memory,
        )


ChatPipelineProviders = [
    ChatAgentProvider(),
    ChatOrchestratorProvider(),
    ChatWithTeamUseCaseProvider(),
]
