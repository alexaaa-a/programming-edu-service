import logging

from dishka import Provider, Scope, provide

from agent_service.app.application.agents.chat_agent import ChatAgent
from agent_service.app.application.graphs import compile_chat_graph
from agent_service.app.application.interfaces import (
    ChatHistoryRepository,
    DecisionModelInterface,
    LLMInterface,
    MemoryInterface,
)
from agent_service.app.config import Settings
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.llm_trace import LlmTracer
from agent_service.app.application.orchestrators.chat_orchestrator import (
    ChatAgentProtocol,
    ChatOrchestrator,
)
from agent_service.app.application.interfaces.trajectory_gateway import (
    TrajectoryGatewayInterface,
)
from agent_service.app.application.use_cases import ChatWithTeamUseCase
from agent_service.app.application.use_cases.get_chat_history import GetChatHistoryUseCase
from agent_service.app.infrastructure.checkpoints.langgraph_saver import StoreBackedCheckpointSaver
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
            tracer: LlmTracer,
    ) -> ChatAgentProtocol:
        agent = ChatAgent(llm=llm, memory=memory)
        return ChatAgentWithObservability(agent, logger=logger, metrics=metrics, tracer=tracer)


class ChatOrchestratorProvider(Provider):
    @provide(scope=Scope.APP)
    def chat_orchestrator(
            self,
            chat_agent: ChatAgentProtocol,
            llm: LLMInterface,
            logger: logging.Logger,
            tracer: LlmTracer,
            langgraph_checkpointer: StoreBackedCheckpointSaver,
            decisions: DecisionModelInterface,
            settings: Settings,
    ) -> ChatOrchestrator:
        return ChatOrchestrator(
            chat_agent=chat_agent,
            llm=llm,
            logger=logger,
            tracer=tracer,
            chat_graph=compile_chat_graph(checkpointer=langgraph_checkpointer),
            decisions=decisions,
            min_confidence=settings.jev_settings.min_confidence,
        )


class ChatWithTeamUseCaseProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def chat_with_team_use_case(
            self,
            chat_orchestrator: ChatOrchestrator,
            memory: MemoryInterface,
            tracer: LlmTracer,
            trajectory_gateway: TrajectoryGatewayInterface,
    ) -> ChatWithTeamUseCase:
        return ChatWithTeamUseCase(
            orchestrator=chat_orchestrator,
            memory=memory,
            tracer=tracer,
            trajectory_gateway=trajectory_gateway,
        )


class GetChatHistoryUseCaseProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_chat_history_use_case(
            self,
            history: ChatHistoryRepository,
    ) -> GetChatHistoryUseCase:
        return GetChatHistoryUseCase(history)


ChatPipelineProviders = [
    ChatAgentProvider(),
    ChatOrchestratorProvider(),
    ChatWithTeamUseCaseProvider(),
    GetChatHistoryUseCaseProvider(),
]
