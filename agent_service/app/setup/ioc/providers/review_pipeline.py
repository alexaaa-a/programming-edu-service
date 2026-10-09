import logging

from dishka import Provider, Scope, provide

from agent_service.app.application.agents import AdversarialAgent, BugAgent, ReviewerAgent
from agent_service.app.application.agents.mentor_agent import MentorAgent
from agent_service.app.application.graphs import compile_review_graph
from agent_service.app.application.interfaces import (
    GraphMemoryInterface,
    LLMInterface,
    MemoryEpisodeQueue,
    MemoryInterface,
    StudentProfileRepository,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.llm_trace import LlmTracer
from agent_service.app.application.orchestrators.review_orchestrator import (
    AdversarialAgentProtocol,
    BugAgentProtocol,
    MentorAgentProtocol,
    ReviewOrchestrator,
    ReviewerAgentProtocol,
)
from agent_service.app.application.tools.toolkit import ReviewToolkit
from agent_service.app.config import Settings
from agent_service.app.application.use_cases.review_submission import ReviewSubmissionUseCase
from agent_service.app.infrastructure.checkpoints.langgraph_saver import StoreBackedCheckpointSaver
from agent_service.app.infrastructure.observability.agent_wrappers import (
    AdversarialAgentWithObservability,
    BugAgentWithObservability,
    MentorAgentWithObservability,
    ReviewerAgentWithObservability,
)


class ReviewerAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def reviewer_agent(
            self,
            llm: LLMInterface,
            memory: MemoryInterface,
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer,
    ) -> ReviewerAgentProtocol:
        agent = ReviewerAgent(llm=llm, memory=memory)
        return ReviewerAgentWithObservability(agent, logger=logger, metrics=metrics, tracer=tracer)


class BugAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def bug_agent(
            self,
            llm: LLMInterface,
            memory: MemoryInterface,
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer,
    ) -> BugAgentProtocol:
        agent = BugAgent(llm=llm, memory=memory)
        return BugAgentWithObservability(agent, logger=logger, metrics=metrics, tracer=tracer)


class AdversarialAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def adversarial_agent(
            self,
            llm: LLMInterface,
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer,
    ) -> AdversarialAgentProtocol:
        agent = AdversarialAgent(llm=llm, memory=None)
        return AdversarialAgentWithObservability(agent, logger=logger, metrics=metrics, tracer=tracer)


class MentorAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def mentor_agent(
            self,
            llm: LLMInterface,
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer,
    ) -> MentorAgentProtocol:
        agent = MentorAgent(llm=llm, memory=None)
        return MentorAgentWithObservability(agent, logger=logger, metrics=metrics, tracer=tracer)


class ReviewOrchestratorProvider(Provider):
    @provide(scope=Scope.APP)
    def review_orchestrator(
            self,
            reviewer_agent: ReviewerAgentProtocol,
            bug_agent: BugAgentProtocol,
            mentor_agent: MentorAgentProtocol,
            adversarial_agent: AdversarialAgentProtocol,
            memory: MemoryInterface,
            student_profiles: StudentProfileRepository,
            llm: LLMInterface,
            logger: logging.Logger,
            tracer: LlmTracer,
            langgraph_checkpointer: StoreBackedCheckpointSaver,
            graph_memory: GraphMemoryInterface,
            episode_queue: MemoryEpisodeQueue,
            settings: Settings,
    ) -> ReviewOrchestrator:
        read_graph = settings.graph_memory_settings.read_in_review
        return ReviewOrchestrator(
            reviewer_agent=reviewer_agent,
            bug_agent=bug_agent,
            mentor_agent=mentor_agent,
            adversarial_agent=adversarial_agent,
            toolkit=ReviewToolkit(
                memory,
                logger=logger,
                profiles=student_profiles,
                graph=graph_memory if read_graph else None,
            ),
            memory=memory,
            llm=llm,
            tracer=tracer,
            review_graph=compile_review_graph(checkpointer=langgraph_checkpointer),
            student_profiles=student_profiles,
            episode_queue=episode_queue if graph_memory.enabled else None,
        )


class ReviewSubmissionUseCaseProvider(Provider):
    @provide(scope=Scope.APP)
    def review_submission_use_case(
            self,
            review_orchestrator: ReviewOrchestrator,
            tracer: LlmTracer,
    ) -> ReviewSubmissionUseCase:
        return ReviewSubmissionUseCase(orchestrator=review_orchestrator, tracer=tracer)


ReviewPipelineProviders = [
    ReviewerAgentProvider(),
    BugAgentProvider(),
    AdversarialAgentProvider(),
    MentorAgentProvider(),
    ReviewOrchestratorProvider(),
    ReviewSubmissionUseCaseProvider(),
]
