from datetime import datetime, timezone
from typing import Any

from agent_service.app.application.dto.student_profile import StudentProfile
from agent_service.app.application.interfaces.student_profile import StudentProfileRepository


class MongoStudentProfileRepository(StudentProfileRepository):
    def __init__(self, collection: Any) -> None:
        self._coll = collection

    async def get(self, user_id: str) -> StudentProfile | None:
        key = str(user_id or "").strip()
        if not key:
            return None
        doc = await self._coll.find_one({"user_id": key})
        if doc is None:
            return None
        updated_at = doc.get("updated_at")
        if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        raw_facts = doc.get("facts")
        facts = [str(item) for item in raw_facts if str(item).strip()] if isinstance(raw_facts, list) else []
        last_task_id = doc.get("last_task_id")
        return StudentProfile(
            user_id=key,
            facts=facts,
            updated_at=updated_at if isinstance(updated_at, datetime) else None,
            last_task_id=str(last_task_id) if last_task_id else None,
            reviews_count=int(doc.get("reviews_count") or 0),
        )

    async def save(
            self,
            user_id: str,
            facts: list[str],
            task_id: str | None = None,
    ) -> None:
        key = str(user_id or "").strip()
        clean = [item.strip() for item in facts if item and item.strip()]
        if not key or not clean:
            return
        now = datetime.now(tz=timezone.utc)
        update: dict[str, Any] = {
            "$set": {"facts": clean, "updated_at": now},
            "$inc": {"reviews_count": 1},
            "$setOnInsert": {"user_id": key, "created_at": now},
        }
        if task_id:
            update["$set"]["last_task_id"] = str(task_id)
        await self._coll.update_one({"user_id": key}, update, upsert=True)
