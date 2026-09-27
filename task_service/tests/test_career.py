from task_service.app.application.career import (
    SALARY_BY_GRADE,
    CareerState,
    accept_letter,
    appeal_available,
    consume_emma_session,
    draft_sprint_letter,
    local_round_limit,
    new_intern,
    spend_bonus,
)


def test_new_intern_starts_at_seventy_thousand():
    state = new_intern(7)
    assert state.grade == "intern"
    assert state.salary == 70_000
    assert state.bonus == 0
    assert state.equity == 0
    assert state.raise_blocked is False
    assert state.incident_used is False
    assert state.appeal_used is False
    assert state.letters == ()
    assert state.purchases == ()


def test_salary_ladder():
    assert list(SALARY_BY_GRADE.values()) == [70_000, 110_000, 150_000, 190_000, 240_000]


def test_spend_rejects_unknown_and_empty_bonus():
    state = new_intern(7)
    nxt, err = spend_bonus(state, "yacht")
    assert nxt is None
    assert err == "unknown_item"
    nxt, err = spend_bonus(state, "extra_round", task_id=1)
    assert nxt is None
    assert err == "insufficient_bonus"


def test_spend_deducts_and_records_purchase():
    state = new_intern(7)
    funded = type(state)(
        user_id=state.user_id,
        grade=state.grade,
        salary=state.salary,
        bonus=20_000,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        created_at=state.created_at,
    )
    nxt, err = spend_bonus(funded, "emma_session", task_id=3)
    assert err is None
    assert nxt is not None
    assert nxt.bonus == 10_000
    assert nxt.purchases[0].item == "emma_session"
    assert nxt.purchases[0].price == 10_000
    assert nxt.purchases[0].task_id == 3


def test_clean_sprint_letter_promotes_and_pays_bonus():
    state = new_intern(7)
    letter = draft_sprint_letter(state, [("API", "ok")], trajectory_blocked=False)
    assert letter.kind == "promote"
    assert letter.old_grade == "intern"
    assert letter.new_grade == "junior"
    assert letter.old_salary == 70_000
    assert letter.new_salary == 110_000
    assert letter.bonus_paid == 22_000
    assert len(letter.facts) == 3
    pending = type(state)(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        pending_letter=letter,
        created_at=state.created_at,
    )
    applied = accept_letter(pending)
    assert applied is not None
    assert applied.grade == "junior"
    assert applied.salary == 110_000
    assert applied.bonus == 22_000
    assert applied.raise_blocked is False
    assert applied.pending_letter is None
    assert applied.letters[-1].text.startswith("Спринт чистый")


def test_weak_majority_letter_does_not_raise():
    state = new_intern(7)
    letter = draft_sprint_letter(
        state,
        [("A", "weak"), ("B", "weak"), ("C", "ok")],
        trajectory_blocked=False,
    )
    assert letter.kind == "no_raise"
    assert letter.new_salary == 70_000
    assert letter.bonus_paid == 0
    assert "Слабо закрыты: A, B" in letter.facts[1]


def test_appeal_is_one_per_sprint_from_strong():
    intern = new_intern(7)
    assert appeal_available(intern) is False
    strong = CareerState(
        user_id=7,
        grade="strong",
        salary=190_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        created_at=intern.created_at,
    )
    assert appeal_available(strong) is True
    used = CareerState(
        user_id=7,
        grade="strong",
        salary=190_000,
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=True,
        created_at=intern.created_at,
    )
    assert appeal_available(used) is False


def test_accept_letter_resets_appeal_for_the_next_sprint():
    state = new_intern(7)
    letter = draft_sprint_letter(state, [("A", "ok")], trajectory_blocked=False)
    pending = CareerState(
        user_id=7,
        grade="strong",
        salary=190_000,
        bonus=0,
        equity=0,
        raise_blocked=True,
        incident_used=False,
        appeal_used=True,
        pending_letter=letter,
        created_at=state.created_at,
    )
    applied = accept_letter(pending)
    assert applied is not None
    assert applied.appeal_used is False
    assert applied.pending_letter is None


def test_extra_round_is_local_and_cannot_be_bought_twice():
    state = new_intern(7)
    funded = CareerState(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=40_000,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        created_at=state.created_at,
    )
    bought, err = spend_bonus(funded, "extra_round", task_id=11)
    assert err is None and bought is not None
    assert local_round_limit(bought, 11) == 3
    assert local_round_limit(bought, 12) == 2
    again, err = spend_bonus(bought, "extra_round", task_id=11)
    assert again is None and err == "already_bought"
    hidden, err = spend_bonus(bought, "early_criteria")
    assert hidden is None and err == "needs_task"
    open_grade = CareerState(
        user_id=7,
        grade="junior_plus",
        salary=150_000,
        bonus=40_000,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        created_at=state.created_at,
    )
    skipped, err = spend_bonus(open_grade, "early_criteria", task_id=11)
    assert skipped is None and err == "not_needed"


def test_emma_session_is_one_unused_turn():
    state = new_intern(7)
    funded = CareerState(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=20_000,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        created_at=state.created_at,
    )
    bought, err = spend_bonus(funded, "emma_session", task_id=4)
    assert err is None and bought is not None
    again, err = spend_bonus(bought, "emma_session", task_id=4)
    assert again is None and err == "already_bought"
    used, err = consume_emma_session(bought)
    assert err is None and used is not None
    assert used.purchases[0].used is True
    empty, err = consume_emma_session(used)
    assert empty is None and err == "nothing_to_use"


def test_unspent_bonus_is_replaced_by_the_letter():
    state = new_intern(7)
    funded = CareerState(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=12_000,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        created_at=state.created_at,
    )
    letter = draft_sprint_letter(funded, [("A", "ok")], trajectory_blocked=False)
    pending = CareerState(
        user_id=7,
        grade="intern",
        salary=70_000,
        bonus=12_000,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        pending_letter=letter,
        created_at=state.created_at,
    )
    applied = accept_letter(pending)
    assert applied is not None
    assert applied.bonus == letter.bonus_paid
    assert applied.bonus == 22_000


def test_held_trajectory_freezes_salary():
    state = new_intern(7)
    letter = draft_sprint_letter(state, [("A", "ok")], trajectory_blocked=True)
    assert letter.kind == "frozen"
    assert letter.new_grade == "intern"
    assert "оклад тот же" in letter.text
    assert "можно открывать" in letter.text
