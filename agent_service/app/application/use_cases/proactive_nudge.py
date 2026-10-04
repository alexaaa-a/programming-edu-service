import logging
from dataclasses import dataclass
from typing import Any, Protocol

from agent_service.app.application.decisions.policies import (
    nudge_question,
    nudge_state,
    read_nudge,
)
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.interfaces.decisions import DecisionModelInterface
from agent_service.app.application.interfaces.trajectory_gateway import (
    TrajectoryGatewayInterface,
)
from agent_service.app.application.chat_transcript import chat_thread_id
from agent_service.app.application.team import format_speaker, member_by_id
from agent_service.app.application.trajectory import TrajectorySnapshot


SPEAKER_ID = "emma"
REMEMBER_SEC = 86_400
MAX_MESSAGE_CHARS = 420

SYSTEM_PROMPT = """Ты Эмма, тестировщик в команде. Пишешь студенту первой, он тебя ни о чём не спрашивал.

Правила:
- две-три короткие фразы, по-русски, на «ты», без приветственных формул;
- не пересказывай ревью и не повторяй его формулировки целиком;
- назови то, что видно по фактам, и предложи один конкретный следующий шаг;
- не давай готовый код и не обещай оценку;
- заканчивай вопросом, на который легко ответить одной строкой.

Верни только текст сообщения, без имени и без кавычек."""


@dataclass(frozen=True, slots=True)
class NudgeResult:
    sent: bool = False
    message: str = ""
    speaker_id: str = ""
    speaker_name: str = ""
    speaker_role: str = ""
    kind: str = ""
    task_id: int | None = None
    reason: str = ""


class NudgeMemory(Protocol):
    async def remember(self, key: str, ttl_sec: int) -> bool: ...


class ProactiveNudgeUseCase:
    def __init__(
            self,
            trajectory_gateway: TrajectoryGatewayInterface,
            memory: MemoryInterface,
            llm: LLMInterface | None = None,
            decisions: DecisionModelInterface | None = None,
            guard: NudgeMemory | None = None,
            min_confidence: float = 0.6,
            logger: logging.Logger | None = None,
    ) -> None:
        self._gateway = trajectory_gateway
        self._memory = memory
        self._llm = llm
        self._decisions = decisions
        self._guard = guard
        self._min_confidence = min_confidence
        self._logger = logger or logging.getLogger("agent_service.nudge")

    async def __call__(
            self,
            user_id: str,
            authorization: str,
            session_id: str = "",
            task_title: str | None = None,
    ) -> NudgeResult:
        snapshot = await self._snapshot(authorization)
        if snapshot is None or not snapshot.nudge_kind:
            return NudgeResult(reason="no_signal")

        kind = snapshot.nudge_kind
        task_id = snapshot.nudge_task_id
        if self._guard is not None:
            fresh = await self._guard.remember(f"nudge:{user_id}:{kind}:{task_id}", REMEMBER_SEC)
            if not fresh:
                return NudgeResult(kind=kind, task_id=task_id, reason="already_sent")

        if not await self._worth_writing(snapshot, task_title):
            self._logger.info("nudge.skipped user_id=%s kind=%s reason=model", user_id, kind)
            return NudgeResult(kind=kind, task_id=task_id, reason="model_said_no")

        message = await self._message(snapshot, task_title)
        member = member_by_id(SPEAKER_ID)
        await self._remember_in_chat(user_id, session_id, member, message)
        self._logger.info("nudge.sent user_id=%s kind=%s task_id=%s", user_id, kind, task_id)
        return NudgeResult(
            sent=True,
            message=message,
            speaker_id=SPEAKER_ID,
            speaker_name=member.name if member else "Эмма",
            speaker_role=member.role if member else "Тестировщик",
            kind=kind,
            task_id=task_id,
            reason=snapshot.nudge_detail,
        )

    async def _snapshot(self, authorization: str) -> TrajectorySnapshot | None:
        if not authorization:
            return None
        try:
            return await self._gateway.get_trajectory(authorization)
        except Exception:
            self._logger.exception("nudge.trajectory.failed")
            return None

    async def _worth_writing(
            self,
            snapshot: TrajectorySnapshot,
            task_title: str | None,
    ) -> bool:
        if self._decisions is None:
            return True
        try:
            answers = await self._decisions.ask(
                state=nudge_state(
                    kind=snapshot.nudge_kind,
                    hours_since=snapshot.nudge_hours,
                    score=snapshot.nudge_score,
                    task_title=task_title,
                    failed_criteria=snapshot.failed_criteria,
                ),
                questions=[nudge_question(snapshot.nudge_kind, snapshot.nudge_detail)],
                label="nudge",
            )
        except Exception:
            self._logger.exception("nudge.decision.failed")
            return True
        return read_nudge(answers, self._min_confidence)

    async def _message(self, snapshot: TrajectorySnapshot, task_title: str | None) -> str:
        fallback = _fallback_message(snapshot, task_title)
        if self._llm is None:
            return fallback
        try:
            raw = await self._llm.generate(SYSTEM_PROMPT, _user_prompt(snapshot, task_title))
        except Exception:
            self._logger.exception("nudge.llm.failed")
            return fallback
        text = " ".join((raw or "").split())
        if not text:
            return fallback
        return text[:MAX_MESSAGE_CHARS]

    async def _remember_in_chat(
            self,
            user_id: str,
            session_id: str,
            member: Any,
            message: str,
    ) -> None:
        header = format_speaker(member) if member is not None else "Эмма (Тестировщик)"
        thread = chat_thread_id(user_id, session_id or f"nudge-{user_id}", None)
        try:
            await self._memory.append_chat_message(
                thread,
                role="assistant",
                content=f"[{header}] {message}",
            )
        except Exception:
            self._logger.exception("nudge.history.failed")


def _user_prompt(snapshot: TrajectorySnapshot, task_title: str | None) -> str:
    lines: list[str] = []
    if snapshot.nudge_kind == "repeat":
        lines.append(
            "Факт: студент отправил на ревью почти то же решение, что и в прошлый раз."
        )
    else:
        lines.append(
            f"Факт: ревью отказало, прошло {snapshot.nudge_hours} ч, новой сдачи нет."
        )
    if task_title:
        lines.append(f"Задача: {task_title}")
    if snapshot.nudge_score is not None:
        lines.append(f"Последний балл: {snapshot.nudge_score}/10")
    if snapshot.failed_criteria:
        lines.append("Не закрыты критерии: " + "; ".join(snapshot.failed_criteria[:3]))
    if snapshot.focus_title:
        lines.append(f"Слабое место по траектории: {snapshot.focus_title}")
    lines.append("Напиши сообщение студенту.")
    return "\n".join(lines)


def _fallback_message(snapshot: TrajectorySnapshot, task_title: str | None) -> str:
    criterion = snapshot.failed_criteria[0] if snapshot.failed_criteria else ""
    where = f" по задаче «{task_title}»" if task_title else ""
    if snapshot.nudge_kind == "repeat":
        tail = f" Самое заметное — «{criterion}»." if criterion else ""
        return (
            f"Привет. Вторая сдача{where} почти не отличается от первой, "
            f"значит замечание я объяснила плохо.{tail} "
            "Скажи, какое место непонятно, и разберём его по шагам."
        )
    tail = f" Начать проще всего с «{criterion}»." if criterion else ""
    return (
        f"Привет. Вижу, после ревью{where} работа встала.{tail} "
        "Напиши, где застопорилось, — вместе найдём, с чего продолжить."
    )
