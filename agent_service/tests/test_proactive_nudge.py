import asyncio
import logging

from agent_service.app.application.decisions.questions import Answers
from agent_service.app.application.trajectory import TrajectorySnapshot
from agent_service.app.application.use_cases.proactive_nudge import ProactiveNudgeUseCase


def snapshot(kind: str = "repeat", **over) -> TrajectorySnapshot:
    data = dict(
        action="revise",
        reason="",
        nudge_kind=kind,
        nudge_task_id=105,
        nudge_hours=8,
        nudge_score=5,
        nudge_detail="вторая сдача почти не отличается от первой",
        failed_criteria=["Скидка округляется вниз до копейки"],
        focus_title="Граничные случаи",
    )
    data.update(over)
    return TrajectorySnapshot(**data)


class _Gateway:
    def __init__(self, result: TrajectorySnapshot | None) -> None:
        self.result = result
        self.calls = 0

    async def get_trajectory(self, authorization: str, task_id: int | None = None):
        self.calls += 1
        return self.result


class _Memory:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    async def append_chat_message(self, session_id, role, content, turn_id=None) -> None:
        self.messages.append((session_id, role, content))


class _LLM:
    def __init__(self, answer: str = "Привет! Вижу, вторая сдача такая же. Что именно непонятно?") -> None:
        self.answer = answer
        self.prompts: list[str] = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        if self.answer is None:
            raise RuntimeError("модель недоступна")
        return self.answer


class _Guard:
    def __init__(self, fresh: bool = True) -> None:
        self.fresh = fresh
        self.keys: list[str] = []

    async def remember(self, key: str, ttl_sec: int) -> bool:
        self.keys.append(key)
        return self.fresh


class _Decisions:
    def __init__(self, probability: float | None) -> None:
        self.probability = probability
        self.asked: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    async def ask(self, state, questions, label=""):
        self.asked.append(label)
        if self.probability is None:
            return Answers(items={})
        return Answers(items={"write_first": float(self.probability)})


def use_case(**over) -> ProactiveNudgeUseCase:
    kwargs = dict(
        trajectory_gateway=_Gateway(snapshot()),
        memory=_Memory(),
        llm=_LLM(),
        decisions=None,
        guard=_Guard(),
        logger=logging.getLogger("test"),
    )
    kwargs.update(over)
    return ProactiveNudgeUseCase(**kwargs)


def run(uc: ProactiveNudgeUseCase, **over):
    kwargs = dict(user_id="7", authorization="Bearer t", session_id="s", task_title="Сумма заказа")
    kwargs.update(over)
    return asyncio.run(uc(**kwargs))


def test_emma_writes_when_the_student_resubmits_the_same_code():
    memory = _Memory()
    llm = _LLM()
    result = run(use_case(memory=memory, llm=llm))

    assert result.sent is True
    assert result.speaker_id == "emma"
    assert result.kind == "repeat"
    assert "то же решение" in llm.prompts[0]
    assert "Скидка округляется вниз до копейки" in llm.prompts[0]
    session, role, content = memory.messages[0]
    assert role == "assistant"
    assert content.startswith("[Эмма (Тестировщик)]")
    assert result.message in content


def test_nothing_is_sent_without_a_signal():
    gateway = _Gateway(snapshot(nudge_kind=""))
    memory = _Memory()
    result = run(use_case(trajectory_gateway=gateway, memory=memory))

    assert result.sent is False and result.reason == "no_signal"
    assert memory.messages == []


def test_the_same_reason_is_not_repeated():
    guard = _Guard(fresh=False)
    memory = _Memory()
    result = run(use_case(guard=guard, memory=memory))

    assert result.sent is False and result.reason == "already_sent"
    assert guard.keys == ["nudge:7:repeat:105"]
    assert memory.messages == []


def test_the_decision_model_can_hold_the_message_back():
    decisions = _Decisions(probability=0.2)
    memory = _Memory()
    result = run(use_case(decisions=decisions, memory=memory))

    assert result.sent is False and result.reason == "model_said_no"
    assert decisions.asked == ["nudge"]
    assert memory.messages == []


def test_a_confident_yes_lets_it_through():
    result = run(use_case(decisions=_Decisions(probability=0.9)))
    assert result.sent is True


def test_an_empty_answer_does_not_block_the_message():
    result = run(use_case(decisions=_Decisions(probability=None)))
    assert result.sent is True


def test_without_a_model_the_text_is_still_human():
    result = run(use_case(llm=None))

    assert result.sent is True
    assert "Вторая сдача" in result.message
    assert "Скидка округляется вниз до копейки" in result.message


def test_a_broken_model_falls_back_to_the_written_text():
    llm = _LLM(answer=None)
    result = run(use_case(llm=llm))

    assert result.sent is True and result.message


def test_the_silence_signal_has_its_own_words():
    gateway = _Gateway(snapshot(kind="silence", nudge_hours=9))
    result = run(use_case(trajectory_gateway=gateway, llm=None))

    assert result.sent is True
    assert "работа встала" in result.message


def test_an_anonymous_call_asks_nothing():
    gateway = _Gateway(snapshot())
    result = run(use_case(trajectory_gateway=gateway), authorization="")

    assert result.sent is False and result.reason == "no_signal"
    assert gateway.calls == 0


def test_the_message_is_short_enough_to_read():
    llm = _LLM(answer="слово " * 500)
    result = run(use_case(llm=llm))
    assert len(result.message) <= 420
