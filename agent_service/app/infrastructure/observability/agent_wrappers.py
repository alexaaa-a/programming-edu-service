from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_service.app.application.orchestrators.chat_orchestrator import (
    ChatAgentProtocol,
)
from agent_service.app.application.orchestrators.review_orchestrator import (
    BugAgentProtocol,
    MentorAgentProtocol,
    ReviewerAgentProtocol,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.metrics import instrument_async
from agent_service.app.application.dto import Review
from agent_service.app.infrastructure.observability.timer import Timer
from agent_service.app.application.observability.tracing import get_trace_id


@dataclass(frozen=True, slots=True)
class AgentRunContext:
    agent_name: str
    tags: dict[str, str]


class ReviewerAgentWithObservability(ReviewerAgentProtocol):
    def __init__(
        self,
        agent: ReviewerAgentProtocol,
        *,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics

    async def run(self, code: str, task_description: str) -> Review:
        ctx = AgentRunContext(
            agent_name="ReviewerAgent",
            tags={
                "code_len": str(len(code)),
                "task_len": str(len(task_description)),
            },
        )
        timer = Timer.start()
        self._logger.info(
            "agent.start trace_id=%s name=%s code_len=%s task_len=%s",
            get_trace_id(),
            ctx.agent_name,
            ctx.tags["code_len"],
            ctx.tags["task_len"],
        )

        async def _call_agent() -> Review:
            return await self._agent.run(code=code, task_description=task_description)
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            result = await decorated()
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "success"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "success"},
            )
            self._logger.info(
                "agent.end trace_id=%s name=%s score=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                result.score,
                timer.elapsed_seconds,
            )
            return result
        except Exception:
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "error"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "error"},
            )
            self._logger.exception(
                "agent.error trace_id=%s name=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                timer.elapsed_seconds,
            )
            raise


class BugAgentWithObservability(BugAgentProtocol):
    def __init__(
        self,
        agent: BugAgentProtocol,
        *,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics

    async def run(self, code: str) -> Review:
        ctx = AgentRunContext(
            agent_name="BugAgent",
            tags={"code_len": str(len(code))},
        )
        timer = Timer.start()
        self._logger.info(
            "agent.start trace_id=%s name=%s code_len=%s",
            get_trace_id(),
            ctx.agent_name,
            ctx.tags["code_len"],
        )

        async def _call_agent() -> Review:
            return await self._agent.run(code=code)
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            result = await decorated()
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "success"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "success"},
            )
            self._logger.info(
                "agent.end trace_id=%s name=%s score=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                result.score,
                timer.elapsed_seconds,
            )
            return result
        except Exception:
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "error"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "error"},
            )
            self._logger.exception(
                "agent.error trace_id=%s name=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                timer.elapsed_seconds,
            )
            raise


class MentorAgentWithObservability(MentorAgentProtocol):
    def __init__(
        self,
        agent: MentorAgentProtocol,
        *,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics

    async def run(self, code: str, results: Any) -> str:
        ctx = AgentRunContext(
            agent_name="MentorAgent",
            tags={"code_len": str(len(code))},
        )
        timer = Timer.start()
        self._logger.info(
            "agent.start trace_id=%s name=%s code_len=%s",
            get_trace_id(),
            ctx.agent_name,
            ctx.tags["code_len"],
        )

        async def _call_agent() -> str:
            return await self._agent.run(code=code, results=results)
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            answer = await decorated()
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "success"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "success"},
            )
            self._logger.info(
                "agent.end trace_id=%s name=%s duration_seconds=%.3f answer_len=%s",
                get_trace_id(),
                ctx.agent_name,
                timer.elapsed_seconds,
                len(answer),
            )
            return answer
        except Exception:
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "error"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "error"},
            )
            self._logger.exception(
                "agent.error trace_id=%s name=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                timer.elapsed_seconds,
            )
            raise


class ChatAgentWithObservability(ChatAgentProtocol):
    def __init__(
        self,
        agent: ChatAgentProtocol,
        *,
        logger: logging.Logger,
        metrics: MetricsRecorder,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics

    async def run(
        self,
        message: str,
        chat_history: list[Any],
        context: Any,
    ) -> str:
        session_id = None
        if isinstance(context, dict):
            session_id = context.get("session_id")

        ctx = AgentRunContext(
            agent_name="ChatAgent",
            tags={
                "session_id": str(session_id) if session_id is not None else "",
                "message_len": str(len(message)),
            },
        )
        timer = Timer.start()
        self._logger.info(
            "agent.start trace_id=%s name=%s session_id=%s message_len=%s",
            get_trace_id(),
            ctx.agent_name,
            ctx.tags["session_id"],
            ctx.tags["message_len"],
        )

        async def _call_agent() -> str:
            return await self._agent.run(message=message, chat_history=chat_history, context=context)
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            answer = await decorated()
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "success"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "success"},
            )
            self._logger.info(
                "agent.end trace_id=%s name=%s session_id=%s duration_seconds=%.3f answer_len=%s",
                get_trace_id(),
                ctx.agent_name,
                ctx.tags["session_id"],
                timer.elapsed_seconds,
                len(answer),
            )
            return answer
        except Exception:
            self._metrics.increment("agent_calls_total", 1, tags={"agent": ctx.agent_name, "status": "error"})
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "error"},
            )
            self._logger.exception(
                "agent.error trace_id=%s name=%s session_id=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                ctx.tags["session_id"],
                timer.elapsed_seconds,
            )
            raise
