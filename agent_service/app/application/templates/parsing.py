import json
from typing import Any

from agent_service.app.application.templates.models import DraftSprint, DraftTask


class ParseError(ValueError):
    pass


def extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ParseError("пустой ответ модели")
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[: -3]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _first_object(raw)
    if not isinstance(parsed, dict):
        raise ParseError("ожидали объект JSON")
    return parsed


def _first_object(text: str) -> Any:
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start: index + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ParseError("в ответе нет корректного JSON")


def compose_description(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    brief = _text(payload.get("brief"))
    if brief:
        parts.append(brief)
    signature = _text(payload.get("signature"))
    if signature:
        parts.append("```python\n" + signature.strip("\n") + "\n```")
    rules = _text(payload.get("rules"))
    if rules:
        parts.append(rules)
    example = _text(payload.get("example"))
    if example:
        parts.append(example if example.lower().startswith("пример") else f"Пример: {example}")
    plan = _lines(payload.get("plan"))
    if plan:
        parts.append("План:\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(plan, 1)))
    criteria = _lines(payload.get("criteria"))
    if criteria:
        parts.append("Критерии приёмки:\n" + "\n".join(f"- {item}" for item in criteria))
    return "\n\n".join(parts).strip() + "\n"


def task_from_payload(payload: dict[str, Any]) -> DraftTask:
    if not isinstance(payload, dict):
        raise ParseError("задача должна быть объектом")
    title = _text(payload.get("title"))
    if not title:
        raise ParseError("у задачи нет названия")
    description = _text(payload.get("description")) or compose_description(payload)
    return DraftTask(
        title=title,
        description=description,
        tests=_code(payload.get("tests")),
        reference=_code(payload.get("reference")),
        broken=_code(payload.get("broken")),
    )


def sprint_from_payload(payload: dict[str, Any], order: int) -> DraftSprint:
    data = payload.get("sprint") if isinstance(payload.get("sprint"), dict) else payload
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ParseError("в ответе нет списка задач")
    tasks: list[DraftTask] = []
    for item in raw_tasks:
        if isinstance(item, dict):
            tasks.append(task_from_payload(item))
    if not tasks:
        raise ParseError("ни одной задачи разобрать не удалось")
    title = _text(data.get("title")) or f"Спринт {order}"
    return DraftSprint(order=order, title=title, tasks=tasks)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value if _text(item)).strip()
    return ""


def _code(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip("\n") + "\n"


def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        items = [line.strip(" -*•\t") for line in value.splitlines()]
    elif isinstance(value, list):
        items = [_text(item).strip(" -*•\t") for item in value]
    else:
        return []
    return [" ".join(item.split()) for item in items if item.strip()]
