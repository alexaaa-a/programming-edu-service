from datetime import datetime

from pydantic import BaseModel, Field


class CareerLetterOut(BaseModel):
    at: datetime
    old_salary: int
    new_salary: int
    bonus_paid: int
    facts: list[str]
    text: str
    kind: str = "promote"
    old_grade: str = "intern"
    new_grade: str = "intern"


class CareerPurchaseOut(BaseModel):
    item: str
    price: int
    at: datetime
    task_id: int | None = None
    used: bool = False


class FridayDemoOut(BaseModel):
    sara_line: str
    question: str
    criterion: str | None = None


class CareerBadgeOut(BaseModel):
    id: str
    title: str
    hint: str
    at: datetime


class CareerQuestOut(BaseModel):
    id: str
    title: str
    hint: str
    current: int
    target: int
    left: int


class CareerProgressOut(BaseModel):
    closes_ok: int = 0
    closes_weak: int = 0
    streak_ok: int = 0
    best_streak: int = 0
    first_try: int = 0
    nines: int = 0
    peer_found: int = 0
    incidents_done: int = 0
    demos_held: int = 0
    sprints: int = 0
    promotions: int = 0
    purchases: int = 0


class CareerOut(BaseModel):
    grade: str
    salary: int
    bonus: int
    equity: int
    raise_blocked: bool
    incident_used: bool
    appeal_used: bool
    letters: list[CareerLetterOut]
    purchases: list[CareerPurchaseOut]
    pending_letter: CareerLetterOut | None = None
    pending_forced: bool = False
    pending_demo: FridayDemoOut | None = None
    progress: CareerProgressOut = CareerProgressOut()
    badges: list[CareerBadgeOut] = []
    quests: list[CareerQuestOut] = []
    badge_total: int = 0


class FridayDemoIn(BaseModel):
    pitch: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=2000)


class SpendBonusIn(BaseModel):
    item: str = Field(min_length=1, max_length=64)
    task_id: int | None = None
