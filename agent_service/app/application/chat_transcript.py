def chat_thread_id(user_id: str | None, session_id: str, task_id: int | None = None) -> str:
    owner = (user_id or "").strip()
    if owner:
        scope = f"task:{int(task_id)}" if task_id is not None else "general"
        return f"u{owner}:{scope}"
    return session_id


def transcript_message(row: object) -> dict[str, str | None]:
    role = _field(row, "role") or "user"
    content = _field(row, "content")
    turn_id = _field(row, "turn_id") or _field(row, "timestamp") or role
    created_at = _field(row, "timestamp")
    sender: str | None = None
    text = content
    if role == "assistant":
        parsed = _parse_assistant_header(content)
        if parsed is not None:
            name, member_role, answer = parsed
            sender = f"{name} ({member_role})" if member_role else name
            text = answer
    return {
        "id": f"{turn_id}:{role}",
        "role": role,
        "text": text,
        "sender": sender,
        "created_at": created_at,
    }


def _field(row: object, key: str) -> str:
    if isinstance(row, dict):
        value = row.get(key)
    else:
        value = getattr(row, key, None)
    if value is None:
        return ""
    return str(value)


def _parse_assistant_header(content: str) -> tuple[str, str, str] | None:
    text = (content or "").strip()
    if not text.startswith("["):
        return None
    close = text.find("]")
    if close <= 1:
        return None
    header = text[1:close].strip()
    answer = text[close + 1:].strip()
    if " (" in header and header.endswith(")"):
        name, member_role = header.rsplit(" (", 1)
        return name.strip(), member_role[:-1].strip(), answer
    return header, "", answer
