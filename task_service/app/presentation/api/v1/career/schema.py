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


class FridayDemoIn(BaseModel):
    pitch: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=2000)


class SpendBonusIn(BaseModel):
    item: str = Field(min_length=1, max_length=64)
    task_id: int | None = None
