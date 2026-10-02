from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from task_service.app.application.quests import (
    CareerBadge,
    CareerProgress,
    apply_purchase,
    apply_sprint,
    award,
)

Grade = str

GRADES: tuple[str, ...] = ("intern", "junior", "junior_plus", "strong", "offer")

SALARY_BY_GRADE: dict[str, int] = {
    "intern": 70_000,
    "junior": 110_000,
    "junior_plus": 150_000,
    "strong": 190_000,
    "offer": 240_000,
}

SPEND_CATALOG: dict[str, int] = {
    "extra_round": 15_000,
    "emma_session": 10_000,
    "early_criteria": 8_000,
}

EQUITY_GRANT = 12_000
INCIDENT_BONUS = 15_000


@dataclass(frozen=True, slots=True)
class CareerLetter:
    at: datetime
    old_salary: int
    new_salary: int
    bonus_paid: int
    facts: tuple[str, ...]
    text: str
    kind: str = "promote"
    old_grade: str = "intern"
    new_grade: str = "intern"


@dataclass(frozen=True, slots=True)
class CareerPurchase:
    item: str
    price: int
    at: datetime
    task_id: int | None = None
    used: bool = False


@dataclass(frozen=True, slots=True)
class FridayDemo:
    sara_line: str
    question: str
    criterion: str | None = None
    trajectory_blocked: bool = False


@dataclass(frozen=True, slots=True)
class CareerState:
    user_id: int
    grade: str
    salary: int
    bonus: int
    equity: int
    raise_blocked: bool
    incident_used: bool
    appeal_used: bool
    letters: tuple[CareerLetter, ...] = ()
    purchases: tuple[CareerPurchase, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    pending_letter: CareerLetter | None = None
    pending_forced: bool = False
    pending_demo: FridayDemo | None = None
    progress: CareerProgress = CareerProgress()
    badges: tuple[CareerBadge, ...] = ()


APPEAL_GRADES = frozenset({"strong", "offer"})


def appeal_available(state: CareerState | None) -> bool:
    if state is None or state.pending_letter is not None or state.pending_demo is not None:
        return False
    return state.grade in APPEAL_GRADES and not state.appeal_used


def new_intern(user_id: int, *, now: datetime | None = None) -> CareerState:
    stamp = now or datetime.now(tz=timezone.utc)
    return CareerState(
        user_id=user_id,
        grade="intern",
        salary=SALARY_BY_GRADE["intern"],
        bonus=0,
        equity=0,
        raise_blocked=False,
        incident_used=False,
        appeal_used=False,
        letters=(),
        purchases=(),
        created_at=stamp,
    )


def local_round_limit(state: CareerState | None, task_id: int, base: int = 2) -> int:
    if state is None:
        return base
    bought = any(
        purchase.item == "extra_round" and purchase.task_id == task_id
        for purchase in state.purchases
    )
    return base + 1 if bought else base


def criteria_unlocked(state: CareerState | None, task_id: int) -> bool:
    if state is None:
        return False
    return any(
        purchase.item == "early_criteria" and purchase.task_id == task_id
        for purchase in state.purchases
    )


def unused_emma_session(state: CareerState | None) -> bool:
    if state is None:
        return False
    return any(purchase.item == "emma_session" and not purchase.used for purchase in state.purchases)


def spend_bonus(
        state: CareerState,
        item: str,
        task_id: int | None = None,
        now: datetime | None = None,
) -> tuple[CareerState | None, str | None]:
    if item not in SPEND_CATALOG:
        return None, "unknown_item"
    if item in {"extra_round", "early_criteria"} and task_id is None:
        return None, "needs_task"
    if item == "early_criteria" and state.grade in {"junior_plus", "strong", "offer"}:
        return None, "not_needed"
    if item in {"extra_round", "early_criteria"} and any(
            purchase.item == item and purchase.task_id == task_id
            for purchase in state.purchases
    ):
        return None, "already_bought"
    if item == "emma_session" and unused_emma_session(state):
        return None, "already_bought"
    price = SPEND_CATALOG[item]
    if state.bonus < price:
        return None, "insufficient_bonus"
    stamp = now or datetime.now(tz=timezone.utc)
    purchase = CareerPurchase(item=item, price=price, at=stamp, task_id=task_id)
    progress = apply_purchase(state.progress)
    badges, _unlocked = award(progress, state.badges, now=stamp)
    return (
        replace(
            state,
            bonus=state.bonus - price,
            purchases=state.purchases + (purchase,),
            progress=progress,
            badges=badges,
        ),
        None,
    )


def consume_emma_session(state: CareerState) -> tuple[CareerState | None, str | None]:
    found = False
    purchases: list[CareerPurchase] = []
    for purchase in state.purchases:
        if not found and purchase.item == "emma_session" and not purchase.used:
            purchases.append(
                CareerPurchase(
                    item=purchase.item,
                    price=purchase.price,
                    at=purchase.at,
                    task_id=purchase.task_id,
                    used=True,
                )
            )
            found = True
        else:
            purchases.append(purchase)
    if not found:
        return None, "nothing_to_use"
    return replace(state, purchases=tuple(purchases)), None


def offer_equity(state: CareerState, kind: str, new_grade: str) -> int:
    if state.equity:
        return state.equity
    if new_grade != "offer" or kind != "promote":
        return 0
    if any(letter.kind != "promote" for letter in state.letters):
        return 0
    return EQUITY_GRANT


def mark_incident_used(state: CareerState) -> CareerState:
    if state.incident_used:
        return state
    return replace(state, incident_used=True)


def clear_incident_used(state: CareerState) -> CareerState:
    if not state.incident_used:
        return state
    return replace(state, incident_used=False)


def _next_grade(grade: str) -> str:
    try:
        index = GRADES.index(grade)
    except ValueError:
        index = 0
    return GRADES[min(index + 1, len(GRADES) - 1)]


def _with_demo_fact(
        facts: tuple[str, str, str],
        kind: str,
        demo_held: bool | None,
) -> tuple[str, ...]:
    if demo_held is None:
        return facts
    if kind == "promote" and demo_held:
        line = "Пятничное демо: питч на месте. Премия целиком."
    elif kind == "promote":
        line = "Пятничное демо: питч тонкий. Премия вполовину."
    elif demo_held:
        line = "Пятничное демо: питч на месте. Грейд по закрытиям."
    else:
        line = "Пятничное демо: питч тонкий. Грейд по закрытиям."
    return facts + (line,)


def _with_incident(
        facts: tuple[str, ...],
        bonus: int,
        incident: str | None,
) -> tuple[tuple[str, ...], int]:
    if incident == "done":
        return (
            facts + (f"Ночной инцидент закрыт. Разовая премия {INCIDENT_BONUS}.",),
            bonus + INCIDENT_BONUS,
        )
    if incident == "weak":
        return (
            facts + ("Ночной инцидент закрыт слабо. Премии за него нет.",),
            bonus,
        )
    if incident == "skipped":
        return (
            facts + ("Ночной инцидент: на проде так и 500. Оклад не трогаем.",),
            bonus,
        )
    return facts, bonus


def _john_with_incident(text: str, incident: str | None) -> str:
    if incident != "done":
        return text
    swapped = text.replace(
        "премии в этом спринте нет",
        f"премии за задачи нет, за ночной инцидент — {INCIDENT_BONUS}",
    )
    if swapped != text:
        return swapped
    return text.replace(
        "— Джон, тимлид",
        f"Ночной инцидент закрыт, разовая премия {INCIDENT_BONUS}. — Джон, тимлид",
    )


def _with_cliff(
        facts: tuple[str, ...],
        state: CareerState,
        kind: str,
        new_grade: str,
) -> tuple[str, ...]:
    if new_grade != "offer" or state.grade == "offer":
        return facts
    if offer_equity(state, kind, new_grade):
        return facts + (f"Опцион: {EQUITY_GRANT}. Cliff пройден.",)
    return facts + ("Опцион: cliff не пройден.",)


def draft_sprint_letter(
        state: CareerState,
        tasks: list[tuple[str, str | None]],
        trajectory_blocked: bool,
        now: datetime | None = None,
        demo_held: bool | None = None,
        incident: str | None = None,
) -> CareerLetter:
    stamp = now or datetime.now(tz=timezone.utc)
    ok_count = sum(1 for _, quality in tasks if (quality or "") == "ok")
    weak_count = sum(1 for _, quality in tasks if (quality or "") == "weak")
    weak_titles = [title for title, quality in tasks if (quality or "") == "weak"]
    facts = (
        f"Зачёт: {ok_count}. Слабо: {weak_count}.",
        "Слабо закрыты: " + ", ".join(weak_titles) if weak_titles else "Слабых закрытий нет.",
        "Траектория держит следующий спринт."
        if trajectory_blocked
        else "Траектория отпускает дальше.",
    )
    old_grade = state.grade if state.grade in GRADES else "intern"
    if trajectory_blocked:
        kind = "frozen"
        new_grade = old_grade
        text = (
            "Траектория ещё тонкая: оклад тот же, премии нет. Следующий спринт можно открывать. "
            "— Джон, тимлид"
        )
    elif weak_count * 2 > len(tasks) or ok_count <= weak_count:
        kind = "no_raise"
        new_grade = old_grade
        text = (
            "Зачётов не большинство. Оклад тот же, премии в этом спринте нет. "
            "— Джон, тимлид"
        )
    else:
        kind = "promote"
        new_grade = _next_grade(old_grade)
        if demo_held is False:
            text = (
                "Спринт чистый по задачам. Грейд выше, премия вполовину: пятничный питч не держался. "
                "— Джон, тимлид"
                if new_grade != old_grade
                else "Потолок грейда уже взят. Питч тонкий — премия вполовину, оклад тот же. "
                "— Джон, тимлид"
            )
        else:
            text = (
                "Спринт чистый. Грейд выше, к окладу — премия двадцать процентов. "
                "— Джон, тимлид"
                if new_grade != old_grade
                else "Потолок грейда уже взят. Премия двадцать процентов, оклад тот же. "
                "— Джон, тимлид"
            )
    new_salary = SALARY_BY_GRADE[new_grade]
    bonus = int(new_salary * 0.2) if kind == "promote" else 0
    facts = _with_demo_fact(facts, kind, demo_held)
    if kind == "promote" and demo_held is False:
        bonus = bonus // 2
    facts, bonus = _with_incident(facts, bonus, incident)
    text = _john_with_incident(text, incident)
    facts = _with_cliff(facts, state, kind, new_grade)
    return CareerLetter(
        at=stamp,
        old_salary=state.salary,
        new_salary=new_salary,
        bonus_paid=bonus,
        facts=facts,
        text=text,
        kind=kind,
        old_grade=old_grade,
        new_grade=new_grade,
    )


def accept_letter(state: CareerState, now: datetime | None = None) -> CareerState | None:
    letter = state.pending_letter
    if letter is None:
        return None
    progress = apply_sprint(
        state.progress,
        promoted=letter.kind == "promote" and letter.new_grade != letter.old_grade,
    )
    badges, _unlocked = award(progress, state.badges, now=now or letter.at)
    return replace(
        state,
        grade=letter.new_grade,
        salary=letter.new_salary,
        bonus=letter.bonus_paid,
        equity=offer_equity(state, letter.kind, letter.new_grade),
        raise_blocked=letter.kind != "promote",
        appeal_used=False,
        letters=state.letters + (letter,),
        pending_letter=None,
        pending_forced=False,
        pending_demo=None,
        progress=progress,
        badges=badges,
    )
