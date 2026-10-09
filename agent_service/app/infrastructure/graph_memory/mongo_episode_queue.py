import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pymongo import ReturnDocument

from agent_service.app.application.graph_memory.facts import MemoryEpisode
from agent_service.app.application.interfaces.memory_episode_queue import MemoryEpisodeQueue


PENDING = "pending"
WORKING = "working"
DONE = "done"
DEAD = "dead"


class MongoMemoryEpisodeQueue(MemoryEpisodeQueue):
    def __init__(
            self,
            collection: Any,
            logger: logging.Logger | None = None,
            lease_sec: int = 300,
            max_attempts: int = 4,
            retry_base_sec: int = 60,
            keep_done_hours: int = 72,
            clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._coll = collection
        self._clock = clock or _now
        self._logger = logger or logging.getLogger(__name__)
        self._lease_sec = lease_sec
        self._max_attempts = max_attempts
        self._retry_base_sec = retry_base_sec
        self._keep_done_hours = keep_done_hours

    async def enqueue(self, episode: MemoryEpisode) -> bool:
        if not episode.episode_id or not episode.user_id:
            return False
        now = self._clock()
        document = episode.as_document()
        try:
            result = await self._coll.update_one(
                {"episode_id": episode.episode_id},
                {
                    "$setOnInsert": {
                        **document,
                        "status": PENDING,
                        "attempts": 0,
                        "visible_at": now,
                        "created_at": now,
                    }
                },
                upsert=True,
            )
        except Exception:
            self._logger.exception("memory_queue.enqueue_failed episode=%s", episode.episode_id)
            return False
        return bool(getattr(result, "upserted_id", None))

    async def claim(self, limit: int, now: datetime | None = None) -> list[MemoryEpisode]:
        moment = now or self._clock()
        lease_until = moment + timedelta(seconds=self._lease_sec)
        claimed: list[MemoryEpisode] = []
        for _ in range(max(0, int(limit))):
            try:
                doc = await self._coll.find_one_and_update(
                    {
                        "status": {"$in": [PENDING, WORKING]},
                        "visible_at": {"$lte": moment},
                    },
                    {
                        "$set": {"status": WORKING, "visible_at": lease_until},
                        "$inc": {"attempts": 1},
                    },
                    sort=[("created_at", 1)],
                    return_document=ReturnDocument.AFTER,
                )
            except Exception:
                self._logger.exception("memory_queue.claim_failed")
                break
            if not doc:
                break
            claimed.append(MemoryEpisode.from_document(doc))
        return claimed

    async def mark_done(self, episode_id: str, facts_written: int = 0) -> None:
        try:
            await self._coll.update_one(
                {"episode_id": episode_id},
                {
                    "$set": {
                        "status": DONE,
                        "finished_at": self._clock(),
                        "facts_written": int(facts_written),
                        "last_error": "",
                    }
                },
            )
        except Exception:
            self._logger.exception("memory_queue.done_failed episode=%s", episode_id)

    async def mark_failed(self, episode_id: str, reason: str) -> None:
        try:
            doc = await self._coll.find_one({"episode_id": episode_id})
        except Exception:
            self._logger.exception("memory_queue.fail_lookup episode=%s", episode_id)
            return
        attempts = int((doc or {}).get("attempts") or 0)
        if attempts >= self._max_attempts:
            update = {"status": DEAD, "finished_at": self._clock(), "last_error": reason[:500]}
        else:
            delay = self._retry_base_sec * (2 ** max(0, attempts - 1))
            update = {
                "status": PENDING,
                "visible_at": self._clock() + timedelta(seconds=min(delay, 3600)),
                "last_error": reason[:500],
            }
        try:
            await self._coll.update_one({"episode_id": episode_id}, {"$set": update})
        except Exception:
            self._logger.exception("memory_queue.fail_update episode=%s", episode_id)

    async def pending_count(self) -> int:
        try:
            return int(await self._coll.count_documents({"status": {"$in": [PENDING, WORKING]}}))
        except Exception:
            return 0

    async def purge_done(self) -> int:
        cutoff = self._clock() - timedelta(hours=self._keep_done_hours)
        try:
            result = await self._coll.delete_many(
                {"status": DONE, "finished_at": {"$lt": cutoff}},
            )
        except Exception:
            self._logger.exception("memory_queue.purge_failed")
            return 0
        return int(getattr(result, "deleted_count", 0) or 0)


async def create_episode_queue(
        collection: Any,
        logger: logging.Logger,
        lease_sec: int = 300,
        max_attempts: int = 4,
        clock: Callable[[], datetime] | None = None,
) -> MongoMemoryEpisodeQueue:
    try:
        await collection.create_index("episode_id", unique=True)
        await collection.create_index([("status", 1), ("visible_at", 1)])
        await collection.create_index([("created_at", 1)])
    except Exception:
        logger.warning("memory_queue.index_failed", exc_info=True)
    return MongoMemoryEpisodeQueue(
        collection,
        logger=logger,
        lease_sec=lease_sec,
        max_attempts=max_attempts,
        clock=clock,
    )


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)
