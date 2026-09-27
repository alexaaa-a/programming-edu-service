import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


HALF_LIFE_DAYS: dict[str, float] = {
    "past_review": 10.0,
    "chat_episode": 5.0,
    "student_note": 21.0,
    "best_practice": 90.0,
    "bugs": 90.0,
}

MAX_AGE_DAYS: dict[str, float | None] = {
    "past_review": 45.0,
    "chat_episode": 21.0,
    "student_note": 120.0,
    "best_practice": None,
    "bugs": None,
}

_DEFAULT_HALF_LIFE = 14.0
_FLUFF_MARKERS = (
    "как языковая модель",
    "я не могу",
    "в качестве ии",
    "as an ai",
    "i am an ai",
    "не имею доступа к",
)
_SOLUTION_DUMP = re.compile(r"```(?:python|javascript|js|ts|java)?\n[\s\S]{400,}```", re.I)


@dataclass(frozen=True, slots=True)
class WriteDecision:
    accept: bool
    text: str
    metadata: dict[str, Any]
    reason: str = ""


def enrich_provenance(
        metadata: dict[str, Any] | None,
        text: str = "",
        now: datetime | None = None,
) -> dict[str, Any]:
    meta = dict(metadata or {})
    stamp = (now or datetime.now(tz=timezone.utc)).isoformat()
    meta.setdefault("saved_at", stamp)
    meta.setdefault("created_at", str(meta.get("saved_at") or stamp))
    doc_type = str(meta.get("type") or "best_practice").strip() or "best_practice"
    meta["type"] = doc_type
    if not str(meta.get("source") or "").strip():
        meta["source"] = _default_source(doc_type)
    if not str(meta.get("writer") or "").strip():
        meta["writer"] = str(meta.get("source") or "unknown")
    for key in ("user_id", "task_id", "session_id", "submission_id", "origin"):
        if key in meta and meta[key] is not None:
            meta[key] = str(meta[key])
    if "verified" not in meta:
        meta["verified"] = 1
    meta["chars"] = int(len(text or ""))
    return meta


def prepare_memory_write(
        text: str,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
) -> WriteDecision:
    meta = enrich_provenance(metadata, text=text or "", now=now)
    doc_type = str(meta["type"])
    compressed = compress_memory_text(text or "", doc_type=doc_type)
    if not compressed:
        return WriteDecision(accept=False, text="", metadata=meta, reason="empty_after_compress")
    ok, reason = validate_memory_text(compressed, doc_type=doc_type, metadata=meta)
    if not ok:
        meta["verified"] = 0
        return WriteDecision(accept=False, text=compressed, metadata=meta, reason=reason)
    meta["verified"] = 1
    meta["chars"] = len(compressed)
    return WriteDecision(accept=True, text=compressed, metadata=meta, reason="ok")


def compress_memory_text(text: str, doc_type: str) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    if doc_type in {"past_review", "chat_episode", "student_note"}:
        cleaned = _SOLUTION_DUMP.sub("[код опущен]", cleaned)
        cleaned = re.sub(r"```.*?```", "[фрагмент опущен]", cleaned, flags=re.S)
        cleaned = " ".join(cleaned.split()).strip()
    limits = {
        "student_note": 400,
        "chat_episode": 900,
        "past_review": 1100,
        "best_practice": 2500,
        "bugs": 2500,
    }
    limit = limits.get(doc_type, 1200)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rsplit(" ", 1)[0].strip() + "…"


def validate_memory_text(
        text: str,
        doc_type: str,
        metadata: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    meta = metadata or {}
    body = (text or "").strip()
    if len(body) < 12:
        return False, "too_short"
    lower = body.lower()
    if any(marker in lower for marker in _FLUFF_MARKERS):
        return False, "llm_fluff"
    if doc_type in {"past_review", "student_note", "chat_episode"}:
        if body.count("def ") >= 3 and "return " in lower:
            return False, "solution_dump"
        if doc_type == "past_review" and "скор" not in lower and "score" not in lower:
            if "правк" not in lower and "ошиб" not in lower and "баг" not in lower:
                if len(body) > 80 and not any(ch.isdigit() for ch in body):
                    return False, "unanchored_review"
        if doc_type == "student_note" and not str(meta.get("user_id") or "").strip():
            return False, "student_note_without_user"
        if doc_type == "past_review" and not str(meta.get("user_id") or "").strip():
            return False, "past_review_without_user"
        if doc_type == "chat_episode" and not str(meta.get("session_id") or "").strip():
            return False, "chat_episode_without_session"
    return True, "ok"


def document_age_days(metadata: dict[str, Any] | None, now: datetime | None = None) -> float | None:
    meta = metadata or {}
    raw = str(meta.get("saved_at") or meta.get("created_at") or "").strip()
    if not raw:
        return None
    try:
        saved = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if saved.tzinfo is None:
            saved = saved.replace(tzinfo=timezone.utc)
        stamp = now or datetime.now(tz=timezone.utc)
        return max((stamp - saved).total_seconds() / 86400.0, 0.0)
    except ValueError:
        return None


def is_fresh(
        metadata: dict[str, Any] | None,
        now: datetime | None = None,
) -> bool:
    meta = metadata or {}
    doc_type = str(meta.get("type") or "")
    max_age = MAX_AGE_DAYS.get(doc_type)
    if max_age is None:
        return True
    age = document_age_days(meta, now=now)
    if age is None:
        return doc_type in {
            "best_practice",
            "bugs",
            "past_review",
            "chat_episode",
            "student_note",
        }
    return age <= max_age


def recency_multiplier(
        metadata: dict[str, Any] | None,
        now: datetime | None = None,
) -> float:
    meta = metadata or {}
    doc_type = str(meta.get("type") or "")
    half_life = HALF_LIFE_DAYS.get(doc_type, _DEFAULT_HALF_LIFE)
    age = document_age_days(meta, now=now)
    if age is None:
        return 1.0
    import math

    return 1.0 + 0.45 * math.exp(-age / max(half_life, 0.1))


def format_provenance(metadata: dict[str, Any] | None, now: datetime | None = None) -> str:
    meta = metadata or {}
    parts: list[str] = []
    doc_type = str(meta.get("type") or "").strip()
    if doc_type:
        parts.append(doc_type)
    source = str(meta.get("source") or "").strip()
    if source:
        parts.append(f"source={source}")
    writer = str(meta.get("writer") or "").strip()
    if writer and writer != source:
        parts.append(f"writer={writer}")
    for key, label in (
        ("task_id", "task"),
        ("user_id", "user"),
        ("session_id", "session"),
        ("submission_id", "submission"),
    ):
        value = str(meta.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
    age = document_age_days(meta, now=now)
    if age is not None:
        if age < 1:
            parts.append("age=<1d")
        else:
            parts.append(f"age={int(age)}d")
    if int(meta.get("verified") or 1) == 0:
        parts.append("unverified")
    return " | ".join(parts)


def _default_source(doc_type: str) -> str:
    return {
        "past_review": "review_pipeline",
        "student_note": "review_pipeline",
        "chat_episode": "chat",
        "best_practice": "knowledge_base",
        "bugs": "knowledge_base",
    }.get(doc_type, "unknown")
