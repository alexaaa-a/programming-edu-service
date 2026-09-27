import logging
from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from task_service.app.application.career import CareerLetter, CareerPurchase, CareerState, FridayDemo
from task_service.app.application.interfaces.db.career_db import CareerDBInterface
from task_service.app.config import Settings


class CareerDB(CareerDBInterface):
    def __init__(
            self,
            client: AsyncIOMotorClient[Any],
            settings: Settings,
            logger: logging.Logger,
    ) -> None:
        self.db = client[settings.mongo_settings.name]["careers"]
        self.logger = logger

    async def get(self, user_id: int) -> CareerState | None:
        try:
            doc = await self.db.find_one({"user_id": user_id})
            if not doc:
                return None
            return _from_doc(doc)
        except Exception:
            self.logger.exception("Failed to get career user_id=%s", user_id)
            return None

    async def save(self, state: CareerState) -> bool:
        try:
            await self.db.update_one(
                {"user_id": state.user_id},
                {"$set": _to_doc(state)},
                upsert=True,
            )
            return True
        except Exception:
            self.logger.exception("Failed to save career user_id=%s", state.user_id)
            return False

    async def delete(self, user_id: int) -> bool:
        try:
            result = await self.db.delete_one({"user_id": user_id})
            return bool(getattr(result, "deleted_count", 0))
        except Exception:
            self.logger.exception("Failed to delete career user_id=%s", user_id)
            return False


def _to_doc(state: CareerState) -> dict[str, Any]:
    return {
        "user_id": state.user_id,
        "grade": state.grade,
        "salary": state.salary,
        "bonus": state.bonus,
        "equity": state.equity,
        "raise_blocked": state.raise_blocked,
        "incident_used": state.incident_used,
        "appeal_used": state.appeal_used,
        "letters": [
            {
                "at": letter.at,
                "old_salary": letter.old_salary,
                "new_salary": letter.new_salary,
                "bonus_paid": letter.bonus_paid,
                "facts": list(letter.facts),
                "text": letter.text,
                "kind": letter.kind,
                "old_grade": letter.old_grade,
                "new_grade": letter.new_grade,
            }
            for letter in state.letters
        ],
        "purchases": [
            {
                "item": purchase.item,
                "price": purchase.price,
                "at": purchase.at,
                "task_id": purchase.task_id,
                "used": purchase.used,
            }
            for purchase in state.purchases
        ],
        "created_at": state.created_at,
        "pending_letter": _letter_doc(state.pending_letter),
        "pending_forced": state.pending_forced,
        "pending_demo": _demo_doc(state.pending_demo),
    }


def _letter_doc(letter: CareerLetter | None) -> dict[str, Any] | None:
    if letter is None:
        return None
    return {
        "at": letter.at,
        "old_salary": letter.old_salary,
        "new_salary": letter.new_salary,
        "bonus_paid": letter.bonus_paid,
        "facts": list(letter.facts),
        "text": letter.text,
        "kind": letter.kind,
        "old_grade": letter.old_grade,
        "new_grade": letter.new_grade,
    }


def _as_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _from_doc(doc: dict[str, Any]) -> CareerState:
    letters = tuple(
        CareerLetter(
            at=_as_dt(item.get("at")),
            old_salary=int(item.get("old_salary") or 0),
            new_salary=int(item.get("new_salary") or 0),
            bonus_paid=int(item.get("bonus_paid") or 0),
            facts=tuple(str(fact) for fact in (item.get("facts") or [])),
            text=str(item.get("text") or ""),
            kind=str(item.get("kind") or "promote"),
            old_grade=str(item.get("old_grade") or "intern"),
            new_grade=str(item.get("new_grade") or "intern"),
        )
        for item in (doc.get("letters") or [])
        if isinstance(item, dict)
    )
    purchases = tuple(
        CareerPurchase(
            item=str(item.get("item") or ""),
            price=int(item.get("price") or 0),
            at=_as_dt(item.get("at")),
            task_id=int(item["task_id"]) if item.get("task_id") is not None else None,
            used=bool(item.get("used")),
        )
        for item in (doc.get("purchases") or [])
        if isinstance(item, dict)
    )
    return CareerState(
        user_id=int(doc["user_id"]),
        grade=str(doc.get("grade") or "intern"),
        salary=int(doc.get("salary") or 0),
        bonus=int(doc.get("bonus") or 0),
        equity=int(doc.get("equity") or 0),
        raise_blocked=bool(doc.get("raise_blocked")),
        incident_used=bool(doc.get("incident_used")),
        appeal_used=bool(doc.get("appeal_used")),
        letters=letters,
        purchases=purchases,
        created_at=_as_dt(doc.get("created_at")),
        pending_letter=_letter_from(doc.get("pending_letter")),
        pending_forced=bool(doc.get("pending_forced")),
        pending_demo=_demo_from(doc.get("pending_demo")),
    )


def _demo_doc(demo: FridayDemo | None) -> dict[str, Any] | None:
    if demo is None:
        return None
    return {
        "sara_line": demo.sara_line,
        "question": demo.question,
        "criterion": demo.criterion,
        "trajectory_blocked": demo.trajectory_blocked,
    }


def _demo_from(raw: Any) -> FridayDemo | None:
    if not isinstance(raw, dict):
        return None
    line = str(raw.get("sara_line") or "").strip()
    question = str(raw.get("question") or "").strip()
    if not line or not question:
        return None
    criterion = raw.get("criterion")
    return FridayDemo(
        sara_line=line,
        question=question,
        criterion=str(criterion) if criterion else None,
        trajectory_blocked=bool(raw.get("trajectory_blocked")),
    )


def _letter_from(raw: Any) -> CareerLetter | None:
    if not isinstance(raw, dict):
        return None
    return CareerLetter(
        at=_as_dt(raw.get("at")),
        old_salary=int(raw.get("old_salary") or 0),
        new_salary=int(raw.get("new_salary") or 0),
        bonus_paid=int(raw.get("bonus_paid") or 0),
        facts=tuple(str(fact) for fact in (raw.get("facts") or [])),
        text=str(raw.get("text") or ""),
        kind=str(raw.get("kind") or "promote"),
        old_grade=str(raw.get("old_grade") or "intern"),
        new_grade=str(raw.get("new_grade") or "intern"),
    )
