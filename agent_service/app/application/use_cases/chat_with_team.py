import hashlib
import uuid

from agent_service.app.application.chat_transcript import chat_thread_id
from agent_service.app.application.dto.chat import ChatTurnResult, ChatWithTeamResult
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.interfaces.trajectory_gateway import (
    TrajectoryGatewayInterface,
)
from agent_service.app.application.orchestrators.chat_orchestrator import ChatOrchestrator
from agent_service.app.application.observability.llm_trace import (
    LlmTracer,
    clip_for_trace,
    get_noop_tracer,
    trace_async,
)
from agent_service.app.application.review.checkpoints import content_hash
from agent_service.app.application.team import format_speaker, member_by_id
from agent_service.app.application.trajectory import format_trajectory_briefing


class ChatWithTeamUseCase:
    def __init__(
            self,
            orchestrator: ChatOrchestrator,
            memory: MemoryInterface,
            tracer: LlmTracer | None = None,
            trajectory_gateway: TrajectoryGatewayInterface | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._memory = memory
        self._tracer = tracer or get_noop_tracer()
        self._trajectory_gateway = trajectory_gateway

    async def __call__(
            self,
            message: str,
            session_id: str,
            task_title: str | None = None,
            task_description: str | None = None,
            task_id: int | None = None,
            authorization: str = "",
            user_id: str | None = None,
            turn_id: str | None = None,
            solo_only: bool = False,
            emma_briefing: str | None = None,
    ) -> ChatWithTeamResult:
        snapshot = None
        if self._trajectory_gateway is not None and authorization:
            try:
                snapshot = await self._trajectory_gateway.get_trajectory(
                    authorization,
                    task_id=task_id,
                )
            except Exception:
                snapshot = None
        briefing = format_trajectory_briefing(snapshot)

        history_key = chat_thread_id(user_id, session_id, task_id)
        history = await self._memory.get_chat_history(history_key)
        client_resume = bool((turn_id or "").strip())
        if client_resume:
            cached = _cached_turn_result(history, message, turn_id=(turn_id or "").strip())
            if cached is not None:
                return ChatWithTeamResult(
                    session_id=session_id,
                    answer=cached["answer"],
                    speaker_id=cached["speaker_id"],
                    speaker_name=cached["speaker_name"],
                    speaker_role=cached["speaker_role"],
                    mode="solo",
                    advisors=[],
                    agent_path=[],
                )

        logical = content_hash(f"{history_key}:{len(history)}:{message}")
        resolved_turn = (turn_id or "").strip() or f"{logical}-{uuid.uuid4().hex[:12]}"

        user_context: dict[str, object] = {
            "session_id": session_id,
            "turn_id": resolved_turn,
        }
        if user_id:
            user_context["user_id"] = str(user_id)
        if task_title:
            user_context["task_title"] = task_title
        if task_description:
            user_context["task_description"] = task_description
        if briefing:
            user_context["trajectory_briefing"] = briefing
        if solo_only:
            user_context["solo_only"] = True
        if (emma_briefing or "").strip():
            user_context["emma_briefing"] = emma_briefing.strip()
        if snapshot is not None:
            user_context["trajectory_action"] = snapshot.action
            if snapshot.focus_mentor:
                user_context["trajectory_mentor"] = snapshot.focus_mentor
            if snapshot.failed_criteria:
                user_context["failed_criteria"] = list(snapshot.failed_criteria[:6])

        async def _run() -> ChatTurnResult:
            return await self._orchestrator.run(
                message=message,
                chat_history=history,
                user_context=user_context,
            )

        turn: ChatTurnResult = await trace_async(
            self._tracer,
            "team-chat",
            _run,
            as_type="chain",
            user_id=user_id,
            session_id=session_id,
            tags=["chat", "mas"],
            input={
                "message": clip_for_trace(message, max_chars=1200),
                "task_title": task_title,
                "task_id": task_id,
                "trajectory_action": snapshot.action if snapshot else None,
                "history_len": len(history),
            },
            metadata={
                "session_id": session_id,
                "user_id": user_id or "",
                "has_task": bool(task_title),
                "has_trajectory": bool(briefing),
            },
            output_from=lambda item: {
                "answer": clip_for_trace(item.answer, max_chars=1800),
                "speaker": item.speaker_id,
                "mode": item.mode,
                "advisors": list(item.advisors),
                "path": [step.name for step in item.agent_path],
            },
            metadata_from=lambda item: {
                "speaker": item.speaker_id,
                "mode": item.mode,
            },
            flush=True,
        )

        member = member_by_id(turn.speaker_id)
        assistant_content = f"[{format_speaker(member)}] {turn.answer}"
        await self._memory.append_chat_message(
            session_id=history_key,
            role="user",
            content=message,
            turn_id=resolved_turn,
        )
        try:
            await self._memory.append_chat_message(
                session_id=history_key,
                role="assistant",
                content=assistant_content,
                turn_id=resolved_turn,
            )
        except Exception:
            try:
                await self._memory.rollback_last_chat_message(
                    session_id=history_key,
                    role="user",
                    content=message,
                )
            except Exception:
                pass
            raise
        await self._remember_episode(
            session_id=session_id,
            user_id=user_id,
            message=message,
            speaker=format_speaker(member),
            answer=turn.answer,
            task_title=task_title,
            task_description=task_description,
        )
        await self._orchestrator.cleanup_turn(message, user_context)

        return ChatWithTeamResult(
            session_id=session_id,
            answer=turn.answer,
            speaker_id=turn.speaker_id,
            speaker_name=turn.speaker_name,
            speaker_role=turn.speaker_role,
            mode=turn.mode,
            advisors=list(turn.advisors),
            agent_path=list(turn.agent_path),
        )

    async def _remember_episode(
            self,
            session_id: str,
            message: str,
            speaker: str,
            answer: str,
            task_title: str | None,
            task_description: str | None = None,
            user_id: str | None = None,
    ) -> None:
        bits = [f"Пользователь: {message.strip()}", f"{speaker}: {answer.strip()}"]
        if task_title:
            bits.insert(0, f"Задача: {task_title}")
        text = "\n".join(bits)
        owner = str(user_id).strip() if user_id else "anon"
        metadata: dict[str, str] = {
            "type": "chat_episode",
            "source": "chat",
            "writer": "chat_with_team",
            "origin": "team_chat",
            "session_id": session_id,
            "id": (
                f"chat_episode_{owner}_{session_id}_"
                f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"
            ),
        }
        if user_id:
            metadata["user_id"] = str(user_id)
        if task_title:
            metadata["task_title"] = task_title[:200]
        if task_description:
            metadata["has_task_context"] = "1"
        try:
            await self._memory.save_document(text[:1200], metadata)
        except Exception:
            return


def _msg_field(item: object, key: str) -> str:
    if isinstance(item, dict):
        return str(item.get(key) or "")
    return str(getattr(item, key, "") or "")


def _parse_assistant_header(content: str) -> tuple[str, str, str] | None:
    text = (content or "").strip()
    if not text.startswith("["):
        return None
    close = text.find("]")
    if close <= 1:
        return None
    header = text[1:close].strip()
    answer = text[close + 1 :].strip()
    if " (" in header and header.endswith(")"):
        name, role = header.rsplit(" (", 1)
        role = role[:-1]
        return name.strip(), role.strip(), answer
    return header, "", answer


def _cached_turn_result(
        history: list[object],
        message: str,
        turn_id: str,
) -> dict[str, str] | None:
    if not turn_id or len(history) < 2:
        return None
    prev, last = history[-2], history[-1]
    if _msg_field(prev, "role") != "user" or _msg_field(prev, "content") != message:
        return None
    if _msg_field(prev, "turn_id") != turn_id:
        return None
    if _msg_field(last, "role") != "assistant":
        return None
    parsed = _parse_assistant_header(_msg_field(last, "content"))
    if parsed is None:
        return None
    name, role, answer = parsed
    from agent_service.app.application.team import TEAM_MEMBERS

    speaker = next((m for m in TEAM_MEMBERS if m.name == name), None)
    if speaker is None:
        speaker = member_by_id("john")
    return {
        "answer": answer,
        "speaker_id": speaker.id,
        "speaker_name": speaker.name,
        "speaker_role": role or speaker.role,
    }
