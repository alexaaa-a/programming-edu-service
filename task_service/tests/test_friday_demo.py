import asyncio
from dataclasses import replace

from task_service.app.application.career import draft_sprint_letter, new_intern
from task_service.app.application.friday_demo import score_friday_demo
from task_service.app.application.interfaces.review_gateway import TrajectoryHint
from task_service.tests.test_complete_sprint import _done, _uc


def test_pitch_needs_two_to_four_sentences_and_a_real_answer():
    pitch = "Собрали поиск по заказам. Клиент находит позицию за один запрос."
    answer = "Критерий закрыли тестом и повторным ревью."
    held, error = score_friday_demo(pitch, answer)
    assert error is None and held is True
    thin, error = score_friday_demo("Только одна фраза про поиск.", answer)
    assert error is None and thin is False
    long_pitch = (
        "Первая фраза здесь. Вторая фраза здесь. Третья фраза здесь. "
        "Четвёртая фраза здесь. Пятая фраза здесь."
    )
    too_long, error = score_friday_demo(long_pitch, answer)
    assert error is None and too_long is False
    empty, error = score_friday_demo("   ", answer)
    assert empty is None and error == "empty"


def test_answer_off_the_criterion_is_a_thin_demo():
    pitch = "Собрали поиск по заказам. Клиент находит позицию за один запрос."
    answer = "Критерий закрыли тестом и повторным ревью."
    held, error = score_friday_demo(pitch, answer, addresses=False)
    assert error is None and held is False
    still, error = score_friday_demo(pitch, answer, addresses=True)
    assert error is None and still is True


def test_thin_demo_halves_bonus_and_leaves_the_grade():
    state = new_intern(7)
    held = draft_sprint_letter(state, [("API", "ok")], trajectory_blocked=False, demo_held=True)
    thin = draft_sprint_letter(state, [("API", "ok")], trajectory_blocked=False, demo_held=False)
    assert held.new_grade == "junior" and thin.new_grade == "junior"
    assert held.new_salary == thin.new_salary == 110_000
    assert held.bonus_paid == 22_000
    assert thin.bonus_paid == 11_000
    assert any("Премия вполовину" in fact for fact in thin.facts)
    frozen = draft_sprint_letter(
        state,
        [("API", "weak")],
        trajectory_blocked=True,
        demo_held=False,
    )
    assert frozen.kind == "frozen"
    assert frozen.new_grade == "intern"
    assert frozen.bonus_paid == 0
    assert any("Грейд по закрытиям" in fact for fact in frozen.facts)


def test_empty_demo_does_not_write_a_letter():
    uc, _, _ = _uc([_done(close_quality="ok")], TrajectoryHint("next_sprint", "ok", False))
    opened = asyncio.run(uc(7, authorization="Bearer t"))
    assert opened.status == "demo"
    assert opened.demo is not None
    assert "в первую очередь" in opened.demo.question
    missed = asyncio.run(uc.submit_demo(7, pitch="  ", answer="  "))
    assert missed.error == "empty"
    stored = asyncio.run(uc.career_db.get(7))
    assert stored is not None and stored.pending_letter is None and stored.pending_demo is not None


def test_model_cuts_the_bonus_when_the_answer_misses_the_criterion():
    class Llm:
        async def grade_demo_answer(self, criterion, answer):
            return "отрицательн" in answer

        async def generate_peer_snippet(self):
            return None

        async def grade_peer_note(self, code, bug, note):
            return None

    uc, _, _ = _uc([_done(close_quality="ok")], TrajectoryHint("next_sprint", "ok", False))
    uc.career_llm = Llm()
    opened = asyncio.run(uc(7, authorization="Bearer t"))
    assert opened.status == "demo"
    state = asyncio.run(uc.career_db.get(7))
    assert state is not None and state.pending_demo is not None
    asyncio.run(uc.career_db.save(replace(
        state,
        pending_demo=replace(state.pending_demo, criterion="проверить отрицательные"),
    )))
    letter = asyncio.run(uc.submit_demo(
        7,
        pitch="Собрали поиск по заказам. Клиент находит позицию за один запрос.",
        answer="Сделали поиск и отдали клиенту быстрее.",
    ))
    assert letter.letter is not None
    assert letter.letter.bonus_paid == 11_000

    again, _, _ = _uc([_done(close_quality="ok")], TrajectoryHint("next_sprint", "ok", False))

    class Down:
        async def grade_demo_answer(self, criterion, answer):
            return None

        async def generate_peer_snippet(self):
            return None

        async def grade_peer_note(self, code, bug, note):
            return None

    again.career_llm = Down()
    asyncio.run(again(7, authorization="Bearer t"))
    stored = asyncio.run(again.career_db.get(7))
    assert stored is not None and stored.pending_demo is not None
    asyncio.run(again.career_db.save(replace(
        stored,
        pending_demo=replace(stored.pending_demo, criterion="проверить отрицательные"),
    )))
    missed = asyncio.run(again.submit_demo(
        7,
        pitch="Собрали поиск по заказам. Клиент находит позицию за один запрос.",
        answer="Отрицательные числа закрыли отдельным тестом.",
    ))
    assert missed.letter is not None
    assert missed.letter.bonus_paid == 22_000
    kept = asyncio.run(again.career_db.get(7))
    assert kept is not None and kept.pending_letter is not None and kept.pending_demo is None
