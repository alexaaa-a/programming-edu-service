import logging

from dishka import Provider, Scope, provide

from agent_service.app.application.agents import BugAgent
from agent_service.app.application.agents.mentor_agent import MentorAgent
from agent_service.app.application.agents import ReviewerAgent
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.orchestrators.review_orchestrator import (
    BugAgentProtocol,
    MentorAgentProtocol,
    ReviewOrchestrator,
    ReviewerAgentProtocol,
)
from agent_service.app.application.use_cases.review_submission import ReviewSubmissionUseCase
from agent_service.app.infrastructure.observability.agent_wrappers import (
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
    ) -> ReviewerAgentProtocol:
        agent = ReviewerAgent(llm=llm, memory=memory)
        return ReviewerAgentWithObservability(agent, logger=logger, metrics=metrics)


class BugAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def bug_agent(
        self,
        llm: LLMInterface,
        memory: MemoryInterface,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> BugAgentProtocol:
        agent = BugAgent(llm=llm, memory=memory)
        return BugAgentWithObservability(agent, logger=logger, metrics=metrics)


class MentorAgentProvider(Provider):
    @provide(scope=Scope.APP)
    def mentor_agent(
        self,
        llm: LLMInterface,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> MentorAgentProtocol:
        agent = MentorAgent(llm=llm, memory=None)
        return MentorAgentWithObservability(agent, logger=logger, metrics=metrics)


class ReviewOrchestratorProvider(Provider):
    @provide(scope=Scope.APP)
    def review_orchestrator(
        self,
        reviewer_agent: ReviewerAgentProtocol,
        bug_agent: BugAgentProtocol,
        mentor_agent: MentorAgentProtocol,
    ) -> ReviewOrchestrator:
        return ReviewOrchestrator(
            reviewer_agent=reviewer_agent,
            bug_agent=bug_agent,
            mentor_agent=mentor_agent,
        )


class ReviewSubmissionUseCaseProvider(Provider):
    @provide(scope=Scope.APP)
    def review_submission_use_case(
        self,
        review_orchestrator: ReviewOrchestrator,
    ) -> ReviewSubmissionUseCase:
        return ReviewSubmissionUseCase(orchestrator=review_orchestrator)


ReviewPipelineProviders = [
    ReviewerAgentProvider(),
    BugAgentProvider(),
    MentorAgentProvider(),
    ReviewOrchestratorProvider(),
    ReviewSubmissionUseCaseProvider(),
]
