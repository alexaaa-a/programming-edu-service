import logging
from dataclasses import dataclass
from typing import Any

from agent_service.app.application.orchestrators.chat_orchestrator import (
    ChatAgentProtocol,
)
from agent_service.app.application.orchestrators.review_orchestrator import (
    AdversarialAgentProtocol,
    BugAgentProtocol,
    MentorAgentProtocol,
    ReviewerAgentProtocol,
)
from agent_service.app.application.observability.metrics_recorder import MetricsRecorder
from agent_service.app.application.observability.metrics import instrument_async
from agent_service.app.application.dto import Review
from agent_service.app.application.review.adversarial import ChallengeVerdict
from agent_service.app.infrastructure.observability.timer import Timer
from agent_service.app.application.observability.tracing import get_trace_id
from agent_service.app.application.observability.llm_trace import LlmTracer, clip_for_trace, get_noop_tracer


@dataclass(frozen=True, slots=True)
class AgentRunContext:
    agent_name: str
    tags: dict[str, str]


class AdversarialAgentWithObservability(AdversarialAgentProtocol):
    def __init__(
            self,
            agent: AdversarialAgentProtocol,
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()

    async def run(
            self,
            code: str,
            task_description: str,
            team_summary: str,
            tool_facts: str = "",
            team_task_score: int = 5,
            team_reliability_score: int = 5,
            tool_findings_errors: int = 0,
            syntax_ok: bool = True,
            compile_ok: bool = True,
            tests_failed: bool = False,
    ) -> ChallengeVerdict:
        ctx = AgentRunContext(
            agent_name="AdversarialAgent",
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

        async def _call_agent() -> ChallengeVerdict:
            return await self._agent.run(
                code=code,
                task_description=task_description,
                team_summary=team_summary,
                tool_facts=tool_facts,
                team_task_score=team_task_score,
                team_reliability_score=team_reliability_score,
                tool_findings_errors=tool_findings_errors,
                syntax_ok=syntax_ok,
                compile_ok=compile_ok,
                tests_failed=tests_failed,
            )

        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            with self._tracer.observation(
                ctx.agent_name,
                as_type="agent",
                input={
                    "code": clip_for_trace(code, max_chars=1500),
                    "task_description": clip_for_trace(task_description, max_chars=800),
                    "team_summary": clip_for_trace(team_summary, max_chars=800),
                },
                metadata={
                    "team_task_score": team_task_score,
                    "team_reliability_score": team_reliability_score,
                    "syntax_ok": syntax_ok,
                    "compile_ok": compile_ok,
                    "tests_failed": tests_failed,
                },
            ) as obs:
                result = await decorated()
                obs.update(
                    output={
                        "agrees": result.agrees,
                        "severity": result.severity,
                    },
                    metadata={"agrees": result.agrees, "severity": result.severity},
                )
                obs.score("agrees", bool(result.agrees), data_type="BOOLEAN")
            self._metrics.increment(
                "agent_calls_total",
                1,
                tags={"agent": ctx.agent_name, "status": "success"},
            )
            self._metrics.record_duration_seconds(
                "agent_call_duration_seconds",
                timer.elapsed_seconds,
                tags={"agent": ctx.agent_name, "status": "success"},
            )
            self._logger.info(
                "agent.end trace_id=%s name=%s agrees=%s severity=%s duration_seconds=%.3f",
                get_trace_id(),
                ctx.agent_name,
                result.agrees,
                result.severity,
                timer.elapsed_seconds,
            )
            return result
        except Exception:
            self._metrics.increment(
                "agent_calls_total",
                1,
                tags={"agent": ctx.agent_name, "status": "error"},
            )
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


class ReviewerAgentWithObservability(ReviewerAgentProtocol):
    def __init__(
            self,
            agent: ReviewerAgentProtocol,
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()

    async def run(self, code: str, task_description: str, tool_facts: str = "") -> Review:
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
            return await self._agent.run(
                code=code,
                task_description=task_description,
                tool_facts=tool_facts,
            )
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            with self._tracer.observation(
                ctx.agent_name,
                as_type="agent",
                input={
                    "code": clip_for_trace(code, max_chars=1500),
                    "task_description": clip_for_trace(task_description, max_chars=800),
                    "tool_facts": clip_for_trace(tool_facts, max_chars=900),
                },
                metadata={"code_len": len(code), "task_len": len(task_description)},
            ) as obs:
                result = await decorated()
                obs.update(
                    output={
                        "score": result.score,
                        "feedback": clip_for_trace(result.feedback, max_chars=1500),
                        "suggestions": list(result.suggestions)[:8],
                    },
                    metadata={"score": result.score},
                )
                obs.score("agent_score", result.score)
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
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()

    async def run(self, code: str, tool_facts: str = "") -> Review:
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
            return await self._agent.run(code=code, tool_facts=tool_facts)
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            with self._tracer.observation(
                ctx.agent_name,
                as_type="agent",
                input={
                    "code": clip_for_trace(code, max_chars=1500),
                    "tool_facts": clip_for_trace(tool_facts, max_chars=900),
                },
                metadata={"code_len": len(code)},
            ) as obs:
                result = await decorated()
                obs.update(
                    output={
                        "score": result.score,
                        "feedback": clip_for_trace(result.feedback, max_chars=1500),
                        "suggestions": list(result.suggestions)[:8],
                    },
                    metadata={"score": result.score},
                )
                obs.score("agent_score", result.score)
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
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()

    async def run(self, code: str, results: Any, tool_facts: str = "") -> str:
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
            return await self._agent.run(code=code, results=results, tool_facts=tool_facts)
        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name},
            )(_call_agent)
            with self._tracer.observation(
                ctx.agent_name,
                as_type="agent",
                input={
                    "code": clip_for_trace(code, max_chars=1500),
                    "tool_facts": clip_for_trace(tool_facts, max_chars=900),
                },
                metadata={"code_len": len(code)},
            ) as obs:
                answer = await decorated()
                obs.update(
                    output=clip_for_trace(answer, max_chars=2000),
                    metadata={"answer_len": len(answer)},
                )
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
            logger: logging.Logger,
            metrics: MetricsRecorder,
            tracer: LlmTracer | None = None,
    ) -> None:
        self._agent = agent
        self._logger = logger
        self._metrics = metrics
        self._tracer = tracer or get_noop_tracer()

    async def speak(
            self,
            member: Any,
            message: str,
            context: Any,
            chat_history: list[Any],
            briefing: str | None = None,
            voice: str = "user",
    ) -> str:
        session_id = None
        if isinstance(context, dict):
            session_id = context.get("session_id")
        member_id = getattr(member, "id", "unknown")

        ctx = AgentRunContext(
            agent_name=f"Chat:{member_id}",
            tags={
                "session_id": str(session_id) if session_id is not None else "",
                "message_len": str(len(message)),
                "member": str(member_id),
                "voice": voice,
            },
        )
        timer = Timer.start()
        self._logger.info(
            "agent.start trace_id=%s name=%s session_id=%s member=%s voice=%s message_len=%s",
            get_trace_id(),
            ctx.agent_name,
            ctx.tags["session_id"],
            member_id,
            voice,
            ctx.tags["message_len"],
        )

        async def _call_agent() -> str:
            return await self._agent.speak(
                member=member,
                message=message,
                context=context,
                chat_history=chat_history,
                briefing=briefing,
                voice=voice,
            )

        try:
            decorated = instrument_async(
                self._metrics,
                component="agent",
                operation="run",
                tags={"agent": ctx.agent_name, "member": str(member_id)},
            )(_call_agent)
            with self._tracer.observation(
                ctx.agent_name,
                as_type="agent",
                session_id=str(session_id) if session_id else None,
                input={
                    "message": clip_for_trace(message, max_chars=1200),
                    "briefing": clip_for_trace(briefing or "", max_chars=800),
                    "voice": voice,
                    "member": str(member_id),
                },
                metadata={"history_len": len(chat_history), "voice": voice},
            ) as obs:
                answer = await decorated()
                obs.update(
                    output=clip_for_trace(answer, max_chars=2000),
                    metadata={"answer_len": len(answer)},
                )
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
