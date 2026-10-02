from dataclasses import asdict, replace
from datetime import datetime, timezone

from task_service.app.application.career import (
    accept_letter,
    draft_sprint_letter,
    new_intern,
    spend_bonus,
)
from task_service.app.application.quests import (
    BADGES,
    BADGE_BY_ID,
    CareerBadge,
    CareerProgress,
    apply_close,
    apply_demo,
    apply_peer_review,
    apply_sprint,
    award,
    quests,
)
from task_service.app.infrastructure.mongo.career_db import _badges_from, _progress_from, _to_doc


def test_badge_catalog_is_consistent():
    assert len(BADGE_BY_ID) == len(BADGES)
    fields = set(CareerProgress.__slots__)
    for badge in BADGES:
        assert badge.metric in fields, badge.id
        assert badge.target >= 1
        assert badge.title and badge.hint


def test_close_with_pass_grows_the_streak():
    progress = CareerProgress()
    for _ in range(3):
        progress = apply_close(progress, "ok")
    assert (progress.closes_ok, progress.streak_ok, progress.best_streak) == (3, 3, 3)

    progress = apply_close(progress, "weak")
    assert progress.closes_weak == 1
    assert progress.streak_ok == 0
    # лучшая серия остаётся в истории
    assert progress.best_streak == 3


def test_first_try_and_nine_need_the_real_numbers():
    one_shot = apply_close(CareerProgress(), "ok", score=9.5, attempts=1)
    assert one_shot.first_try == 1 and one_shot.nines == 1

    second_round = apply_close(CareerProgress(), "ok", score=8.0, attempts=2)
    assert second_round.first_try == 0 and second_round.nines == 0

    weak = apply_close(CareerProgress(), "weak", score=9.9, attempts=1)
    assert weak.nines == 0 and weak.first_try == 0


def test_badges_are_awarded_once_and_report_what_is_new():
    progress = apply_close(CareerProgress(), "ok", score=10, attempts=1)
    badges, unlocked = award(progress, ())
    assert set(unlocked) == {"first_close", "first_try", "nine"}

    again, nothing = award(progress, badges)
    assert nothing == ()
    assert len(again) == len(badges)


def test_streak_badge_unlocks_exactly_at_the_target():
    progress = CareerProgress()
    badges: tuple[CareerBadge, ...] = ()
    unlocked_at: dict[str, int] = {}
    for step in range(1, 6):
        progress = apply_close(progress, "ok")
        badges, unlocked = award(progress, badges)
        for badge_id in unlocked:
            unlocked_at[badge_id] = step
    assert unlocked_at["streak_three"] == 3
    assert unlocked_at["streak_five"] == 5


def test_quests_show_the_closest_goals_with_numbers():
    progress = apply_close(apply_close(CareerProgress(), "ok"), "ok")
    badges, _ = award(progress, ())
    active = quests(progress, badges)

    assert len(active) == 3
    assert active[0].left <= active[-1].left
    # «ещё один зачёт подряд» ближе, чем нетронутая цель с тем же остатком
    three = active[0]
    assert three.id == "streak_three"
    assert (three.current, three.target, three.left) == (2, 3, 1)
    # выданные бейджи в целях не повторяются
    assert all(item.id not in {badge.id for badge in badges} for item in active)


def test_quests_are_capped_but_never_empty_at_the_start():
    active = quests(CareerProgress(), ())
    assert 0 < len(active) <= 3
    assert all(item.current == 0 for item in active)


def test_peer_review_counts_only_a_real_find():
    assert apply_peer_review(CareerProgress(), found=False).peer_found == 0
    assert apply_peer_review(CareerProgress(), found=True).peer_found == 1


def test_demo_and_incident_counters():
    progress = apply_demo(CareerProgress(), held=True, incident="done")
    assert progress.demos_held == 1 and progress.incidents_done == 1

    weak = apply_demo(CareerProgress(), held=False, incident="weak")
    assert weak.demos_held == 0 and weak.incidents_done == 0


def test_sprint_counts_promotion_separately():
    assert apply_sprint(CareerProgress(), promoted=False) == CareerProgress(sprints=1)
    assert apply_sprint(CareerProgress(), promoted=True) == CareerProgress(sprints=1, promotions=1)


def test_accepting_a_promotion_letter_awards_the_badge():
    state = new_intern(7)
    letter = draft_sprint_letter(
        state,
        [("Задача 1", "ok"), ("Задача 2", "ok")],
        trajectory_blocked=False,
        demo_held=True,
    )
    assert letter.kind == "promote"
    # без письма в состоянии принимать нечего
    assert accept_letter(state) is None

    applied = accept_letter(replace(state, pending_letter=letter))
    assert applied is not None
    assert applied.progress.sprints == 1 and applied.progress.promotions == 1
    assert {badge.id for badge in applied.badges} >= {"promoted"}
    assert applied.grade == letter.new_grade


def test_accepting_a_frozen_letter_counts_the_sprint_but_not_a_promotion():
    state = new_intern(7)
    letter = draft_sprint_letter(
        state,
        [("Задача 1", "weak"), ("Задача 2", "weak")],
        trajectory_blocked=True,
    )
    applied = accept_letter(replace(state, pending_letter=letter))
    assert applied is not None
    assert applied.progress.sprints == 1 and applied.progress.promotions == 0
    assert "promoted" not in {badge.id for badge in applied.badges}


def test_spending_bonus_keeps_progress_and_awards_investor():
    state = replace(new_intern(7), bonus=20_000, progress=CareerProgress(closes_ok=2))
    updated, error = spend_bonus(state, "emma_session")
    assert error is None and updated is not None
    assert updated.progress.purchases == 1
    assert updated.progress.closes_ok == 2
    assert "investor" in {badge.id for badge in updated.badges}


def test_career_document_round_trip_keeps_progress_and_badges():
    now = datetime.now(tz=timezone.utc)
    progress = CareerProgress(closes_ok=4, best_streak=3, nines=1)
    badges = (CareerBadge(id="first_close", at=now),)
    doc = _to_doc(replace(new_intern(7), progress=progress, badges=badges))

    assert doc["progress"] == asdict(progress)
    assert _progress_from(doc["progress"]) == progress
    assert _badges_from(doc["badges"]) == badges


def test_document_reader_survives_junk():
    assert _progress_from(None) == CareerProgress()
    assert _progress_from({"closes_ok": "пять", "unknown": 3}) == CareerProgress()
    assert _progress_from({"closes_ok": -2}) == CareerProgress(closes_ok=0)
    assert _badges_from([{"id": "nope", "at": datetime.now()}, "мусор"]) == ()


def test_badges_are_not_duplicated_by_the_reader():
    now = datetime.now(tz=timezone.utc)
    rows = [{"id": "first_close", "at": now}, {"id": "first_close", "at": now}]
    assert len(_badges_from(rows)) == 1
