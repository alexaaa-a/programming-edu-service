from task_service.app.application.close_gate import ReviewSnapshot

_TAIL = "Осталось с прошлого ревью:"
_MAX_CRITERION = 180


def failed_criterion_from_latest(snapshots: list[ReviewSnapshot] | None) -> str | None:
    if not snapshots:
        return None
    latest = _sorted(snapshots)[-1]
    for raw in latest.failed_criteria:
        text = " ".join(str(raw).split()).strip()
        if text:
            return _clip(text)
    return None


def append_weak_tail(description: str, criterion: str | None) -> str:
    text = " ".join(str(criterion or "").split()).strip()
    if not text:
        return description
    block = f"{_TAIL} {_clip(text)}"
    if block in description:
        return description
    base = description.rstrip()
    if not base:
        return block
    return f"{base}\n\n{block}"


def _clip(text: str) -> str:
    if len(text) <= _MAX_CRITERION:
        return text
    return text[: _MAX_CRITERION - 1].rstrip() + "…"


def _sorted(snapshots: list[ReviewSnapshot]) -> list[ReviewSnapshot]:
    def key(item: ReviewSnapshot) -> str:
        stamp = item.created_at
        if stamp is None:
            return ""
        return stamp.isoformat() if hasattr(stamp, "isoformat") else str(stamp)

    return sorted(snapshots, key=key)
