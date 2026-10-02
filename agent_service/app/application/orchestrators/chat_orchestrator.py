from abc import abstractmethod
import asyncio
import logging
from typing import Any, Protocol

from agent_service.app.application.decisions import (
    ChatTurnPolicy,
    chat_turn_questions,
    chat_turn_state,
    read_chat_turn,
)
from agent_service.app.application.dto.chat import ChatTurnResult, PathStepResult
from agent_service.app.application.interfaces import DecisionModelInterface, LLMInterface
from agent_service.app.application.observability.llm_trace import LlmTracer, get_noop_tracer
from agent_service.app.application.review.agent_path import AgentPath, evaluate_chat_path
from agent_service.app.application.review.checkpoints import content_hash
from agent_service.app.application.review.context_compact import compact_huddle_briefing
from agent_service.app.application.team import TeamMember, member_by_id
from agent_service.app.application.team_router import (
    RouteDecision,
    default_route,
    detect_mention,
    huddle_advisors,
    parse_route_json,
    route_from_policy,
    route_system_prompt,
    emma_session_route,
    limit_to_one_speaker,
    route_without_llm,
)
from agent_service.app.application.graphs.runner import ainvoke_graph
from agent_service.app.application.graphs.state import ChatGraphRuntime
from agent_service.app.application.graphs.runner import delete_graph_thread


class ChatAgentProtocol(Protocol):
    @abstractmethod
    async def speak(
            self,
            member: TeamMember,
            message: str,
            context: Any,
            chat_history: list[Any],
            briefing: str | None = None,
            voice: str = "user",
    ) -> str:
        raise NotImplementedError


class ChatOrchestrator:
    def __init__(
            self,
            chat_agent: ChatAgentProtocol,
            llm: LLMInterface | None = None,
            logger: logging.Logger | None = None,
            tracer: LlmTracer | None = None,
            chat_graph: Any | None = None,
            decisions: DecisionModelInterface | None = None,
            min_confidence: float = 0.6,
    ) -> None:
        self._chat_agent = chat_agent
        self._llm = llm
        self._logger = logger or logging.getLogger("agent_service")
        self._tracer = tracer or get_noop_tracer()
        if chat_graph is None:
            raise ValueError("chat_graph is required")
        self._chat_graph = chat_graph
        self._decisions = decisions
        self._min_confidence = min_confidence

    async def run(
            self,
            message: str,
            chat_history: list[Any],
            user_context: Any,
    ) -> ChatTurnResult:
        path = AgentPath()
        trajectory_action = _trajectory_action(user_context)
        return await self._run_graph(
            message=message,
            chat_history=chat_history,
            user_context=user_context,
            trajectory_action=trajectory_action,
            path=path,
        )

    async def _run_graph(
            self,
            message: str,
            chat_history: list[Any],
            user_context: Any,
            trajectory_action: str | None,
            path: AgentPath,
    ) -> ChatTurnResult:
        thread_id = chat_graph_thread_id(message, user_context)
        self._logger.info("chat.runtime langgraph=full")
        out = await ainvoke_graph(
            self._chat_graph,
            {
                "message": message,
                "chat_history": chat_history,
                "user_context": user_context,
                "trajectory_action": trajectory_action,
                "path": path,
            },
            context=ChatGraphRuntime(orchestrator=self, tracer=self._tracer),
            tracer=self._tracer,
            thread_id=thread_id,
            graph_name="chat",
        )
        result = out.get("result")
        if not isinstance(result, ChatTurnResult):
            raise RuntimeError("langgraph chat graph produced no ChatTurnResult")
        return result

    async def cleanup_turn(self, message: str, user_context: Any) -> None:
        thread_id = chat_graph_thread_id(message, user_context)
        try:
            await delete_graph_thread(self._chat_graph, thread_id)
        except Exception:
            self._logger.exception(
                "chat.delete_thread_failed thread_id=%s (result still ok)",
                thread_id,
            )

    async def step_route(
            self,
            message: str,
            trajectory_action: str | None,
            path: AgentPath,
            solo_only: bool = False,
            emma_session: bool = False,
            trajectory_mentor: str | None = None,
            user_context: Any = None,
            chat_history: list[Any] | None = None,
    ) -> tuple[RouteDecision, AgentPath]:
        policy = await self._decide_turn(message, user_context, chat_history)
        if emma_session:
            decision = emma_session_route()
        else:
            decision = await self._route(
                message,
                trajectory_action=trajectory_action,
                trajectory_mentor=trajectory_mentor,
                policy=policy,
            )
            if solo_only:
                decision = limit_to_one_speaker(decision)
        if policy is not None:
            path.record(
                "coach",
                kind="step",
                status="ok",
                detail=(
                    f"solution_seeking={int(policy.solution_seeking)},"
                    f"frustration={policy.frustration}"
                ),
            )
        path.record(
            "route",
            kind="step",
            status="ok",
            detail=f"mode={decision.mode},speaker={decision.speaker.id},source={decision.source}",
        )
        self._logger.info(
            "chat.route mode=%s speaker=%s source=%s reason=%s",
            decision.mode,
            decision.speaker.id,
            decision.source,
            decision.reason,
        )
        return decision, path

    async def step_solo_speak(
            self,
            message: str,
            chat_history: list[Any],
            user_context: Any,
            speaker: TeamMember,
            path: AgentPath,
    ) -> tuple[str, AgentPath]:
        path.record("speaker", kind="agent", status="ok", detail=speaker.id)
        answer = await self._chat_agent.speak(
            member=speaker,
            message=message,
            context=user_context,
            chat_history=chat_history,
        )
        return answer, path

    async def step_huddle_advisors(
            self,
            message: str,
            chat_history: list[Any],
            user_context: Any,
            speaker: TeamMember,
            path: AgentPath,
    ) -> tuple[str, list[str], AgentPath]:
        advisors = huddle_advisors(message, speaker)
        advisor_ids = [member.id for member in advisors]
        notes_raw = await asyncio.gather(
            *[
                self._chat_agent.speak(
                    member=member,
                    message=message,
                    context=user_context,
                    chat_history=chat_history,
                    voice="internal",
                )
                for member in advisors
            ],
            return_exceptions=True,
        )
        notes: list[str] = []
        for member, note in zip(advisors, notes_raw, strict=False):
            if isinstance(note, BaseException) and not isinstance(note, Exception):
                raise note
            if isinstance(note, Exception):
                self._logger.error(
                    "chat.huddle.advisor_failed advisor=%s: %s",
                    member.id,
                    note,
                )
                path.record(
                    "advisor",
                    kind="agent",
                    status="error",
                    detail=f"{member.id}:failed",
                )
                notes.append(f"(совет от {member.name} недоступен)")
                continue
            path.record("advisor", kind="agent", status="ok", detail=member.id)
            notes.append(str(note))
        briefing = "\n\n".join(
            f"{member.name} ({member.role}):\n{note.strip()}"
            for member, note in zip(advisors, notes, strict=False)
        )
        briefing = compact_huddle_briefing(briefing)
        return briefing, advisor_ids, path

    async def step_huddle_speak(
            self,
            message: str,
            chat_history: list[Any],
            user_context: Any,
            speaker: TeamMember,
            briefing: str,
            path: AgentPath,
    ) -> tuple[str, AgentPath]:
        path.record("speaker", kind="agent", status="ok", detail=speaker.id)
        answer = await self._chat_agent.speak(
            member=speaker,
            message=message,
            context=user_context,
            chat_history=chat_history,
            briefing=briefing,
            voice="user",
        )
        return answer, path

    def step_process_eval(
            self,
            mode: str,
            speaker_id: str,
            advisors: list[str],
            answer: str,
            path: AgentPath,
    ) -> AgentPath:
        verdict = evaluate_chat_path(
            mode=mode,
            speaker_id=speaker_id,
            advisors=advisors,
            answer=answer,
        )
        path.record(
            "process_eval",
            kind="step",
            status="ok" if verdict.ok else "warn",
            detail=f"score={verdict.score}",
        )
        self._logger.info(
            "chat.path mode=%s speaker=%s advisors=%s process=%s violations=%s steps=%s",
            mode,
            speaker_id,
            ",".join(advisors) or "-",
            verdict.score,
            len(verdict.violations),
            ",".join(path.names()),
        )
        return path

    def step_finalize(
            self,
            answer: str,
            speaker_id: str,
            speaker_name: str,
            speaker_role: str,
            mode: str,
            advisors: list[str],
            path: AgentPath,
    ) -> ChatTurnResult:
        speaker = member_by_id(speaker_id)
        return ChatTurnResult(
            answer=answer,
            speaker_id=speaker.id,
            speaker_name=speaker_name or speaker.name,
            speaker_role=speaker_role or speaker.role,
            mode=mode,
            advisors=list(advisors),
            agent_path=[
                PathStepResult(
                    kind=step.kind,
                    name=step.name,
                    status=step.status,
                    detail=step.detail,
                )
                for step in path.steps
            ],
        )

    async def _decide_turn(
            self,
            message: str,
            user_context: Any,
            chat_history: list[Any] | None,
    ) -> ChatTurnPolicy | None:
        if self._decisions is None or not self._decisions.enabled:
            return None
        context = user_context if isinstance(user_context, dict) else {}
        answers = await self._decisions.ask(
            chat_turn_state(
                message=message,
                task_title=context.get("task_title"),
                task_description=context.get("task_description"),
                briefing=context.get("trajectory_briefing"),
                history_tail=_history_tail(chat_history),
            ),
            chat_turn_questions(),
            label="chat_turn",
        )
        policy = read_chat_turn(answers, min_confidence=self._min_confidence)
        if policy is None:
            return None
        lines = policy.coach_lines()
        if lines and isinstance(user_context, dict):
            user_context["coach"] = lines
        self._logger.info(
            "chat.turn.policy speaker=%s huddle=%s solution_seeking=%s frustration=%s "
            "confidence=%.2f latency_ms=%.0f",
            policy.speaker_id or "-",
            policy.huddle,
            policy.solution_seeking,
            policy.frustration,
            policy.confidence,
            answers.latency_ms,
        )
        return policy

    async def _route(
            self,
            message: str,
            trajectory_action: str | None = None,
            trajectory_mentor: str | None = None,
            policy: ChatTurnPolicy | None = None,
    ) -> RouteDecision:
        with self._tracer.observation(
            "chat.route",
            as_type="span",
            input={
                "message": message[:500],
                "trajectory_action": trajectory_action,
                "trajectory_mentor": trajectory_mentor,
            },
        ) as obs:
            decision = await self._route_inner(
                message,
                trajectory_action=trajectory_action,
                trajectory_mentor=trajectory_mentor,
                policy=policy,
            )
            obs.update(
                output={
                    "mode": decision.mode,
                    "speaker": decision.speaker.id,
                    "source": decision.source,
                }
            )
            return decision

    async def _route_inner(
            self,
            message: str,
            trajectory_action: str | None = None,
            trajectory_mentor: str | None = None,
            policy: ChatTurnPolicy | None = None,
    ) -> RouteDecision:
        mentioned = detect_mention(message)
        if mentioned is not None:
            return RouteDecision(
                mode="solo",
                speaker=mentioned,
                reason="пользователь позвал по имени",
                source="mention",
            )
        if policy is not None:
            from_policy = route_from_policy(policy)
            if from_policy is not None:
                return from_policy
        deterministic = route_without_llm(
            message,
            trajectory_action=trajectory_action,
            trajectory_mentor=trajectory_mentor,
        )
        if deterministic is not None:
            return deterministic
        if self._llm is None:
            return default_route()
        try:
            raw = await self._llm.generate(
                route_system_prompt(),
                _route_user_prompt(message, trajectory_action),
            )
            parsed = parse_route_json(raw)
            if parsed is not None:
                return parsed
        except Exception:
            self._logger.exception("chat.route.llm_failed")
        return default_route()


def chat_graph_thread_id(message: str, user_context: Any = None) -> str:
    session_id = ""
    user_id = ""
    turn_id = ""
    if isinstance(user_context, dict):
        session_id = str(user_context.get("session_id") or "")
        user_id = str(user_context.get("user_id") or "")
        turn_id = str(user_context.get("turn_id") or user_context.get("request_id") or "")
    who = user_id or "anon"
    scope = session_id or content_hash(message)
    nonce = turn_id or "t0"
    return f"chat_graph:{who}:{scope}:{content_hash(message)}:{nonce}"


def _trajectory_action(user_context: Any) -> str | None:
    if not isinstance(user_context, dict):
        return None
    raw = user_context.get("trajectory_action")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _history_tail(chat_history: list[Any] | None, limit: int = 4) -> list[str]:
    if not chat_history:
        return []
    tail: list[str] = []
    for item in list(chat_history)[-limit:]:
        if isinstance(item, dict):
            role = str(item.get("role") or "")
            content = str(item.get("content") or "")
        else:
            role = str(getattr(item, "role", "") or "")
            content = str(getattr(item, "content", "") or "")
        if content:
            tail.append(f"{role}: {content}"[:400])
    return tail


def _route_user_prompt(message: str, trajectory_action: str | None) -> str:
    extra = ""
    if trajectory_action == "chat":
        extra = (
            "\nТраектория студента: сейчас нужно разобрать замечания. "
            "Если нет явной другой темы, speaker=sara.\n"
        )
    return f"Сообщение пользователя:\n{message}\n{extra}"
