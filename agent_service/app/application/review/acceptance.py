import json
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol


class LLMLike(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    id: str
    text: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class CriterionCheck:
    id: str
    text: str
    passed: bool
    note: str = ""
    required: bool = True
    line: int | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AcceptanceRubric:
    criteria: list[AcceptanceCriterion] = field(default_factory=list)

    def as_prompt_block(self) -> str:
        if not self.criteria:
            return ""
        lines = [
            "Критерии приёмки по этой задаче (проверяй код именно по ним):",
        ]
        for item in self.criteria:
            mark = "обязательный" if item.required else "желательный"
            lines.append(f"- [{item.id}] ({mark}) {item.text}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        return {"criteria": [asdict(item) for item in self.criteria]}


_BOARD_NOTE = "На доске"
_BOARD_RULE = re.compile(
    r"спринт можно закрыть|"
    r"взял в работу|"
    r"довед\w* до закрытия|"
    r"разов\w+ преми|"
    r"\bоклад\b|"
    r"слабое закрытие|"
    r"молчани\w* преми",
    re.IGNORECASE,
)


def is_board_chatter(text: str) -> bool:
    return bool(_BOARD_RULE.search(text or ""))


def review_brief(task_description: str) -> str:
    text = task_description or ""
    marker = text.find(_BOARD_NOTE)
    if marker >= 0:
        text = text[:marker]
    kept: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        chunk = part.strip()
        if not chunk or _BOARD_RULE.search(chunk):
            continue
        kept.append(chunk)
    return "\n".join(kept).strip()


def build_rubric_heuristic(task_description: str) -> AcceptanceRubric:
    text = review_brief(task_description).strip()
    if not text:
        return AcceptanceRubric(
            criteria=[
                AcceptanceCriterion(
                    id="c1",
                    text="Решение закрывает основное требование задачи",
                    required=True,
                )
            ]
        )

    chunks = _split_requirements(text)
    criteria: list[AcceptanceCriterion] = []
    for index, chunk in enumerate(chunks[:6], start=1):
        criteria.append(
            AcceptanceCriterion(
                id=f"c{index}",
                text=chunk,
                required=True,
            )
        )
    if not criteria:
        criteria.append(
            AcceptanceCriterion(
                id="c1",
                text=_clip(text, 160),
                required=True,
            )
        )
    return AcceptanceRubric(criteria=criteria)


async def build_rubric(llm: LLMLike | None, task_description: str) -> AcceptanceRubric:
    fallback = build_rubric_heuristic(task_description)
    if llm is None:
        return fallback
    system = (
        "Ты составляешь критерии приёмки учебной задачи по программированию.\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"criteria":[{"id":"c1","text":"...","required":true}]}\n'
        "Правила:\n"
        "- 3..6 критериев, каждый проверяемый по коду;\n"
        "- id короткие: c1, c2, ...;\n"
        "- text на русском, <= 140 символов, без markdown;\n"
        "- не пиши общие вещи вроде «код чистый» — только из брифа;\n"
        "- required=true для обязательных условий задачи;\n"
        "- не делай критерием правила доски: спринт, премия, оклад, статус задачи. "
        "Только то, что проверяется по коду.\n"
    )
    user = f"Бриф задачи:\n{review_brief(task_description)}\n"
    try:
        raw = await llm.generate(system, user)
        parsed = _parse_rubric_json(raw)
        if parsed is not None and parsed.criteria:
            return parsed
    except Exception:
        pass
    return fallback


async def grade_rubric(
        llm: LLMLike | None,
        code: str,
        task_description: str,
        rubric: AcceptanceRubric,
        tool_facts: str = "",
) -> list[CriterionCheck]:
    if not rubric.criteria:
        return []
    if llm is None:
        return _grade_heuristic(code=code, rubric=rubric)

    criteria_json = json.dumps(
        [asdict(item) for item in rubric.criteria],
        ensure_ascii=False,
    )
    system = (
        "Ты проверяешь код студента по критериям приёмки.\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"checks":[{"id":"c1","passed":true,"note":"кратко","line":12}]}\n'
        "Правила:\n"
        "- для каждого критерия ровно одна проверка;\n"
        "- passed=true только если требование явно выполнено в коде;\n"
        "- note на русском <= 120 символов;\n"
        "- line — номер строки кода, к которой относится замечание, с единицы;\n"
        "- line ставь только когда уверен в месте, иначе null;\n"
        "- не выдумывай поведение вне кода и фактов инструментов;\n"
        "- если синтаксис/компиляция сломаны — критерии про реализацию скорее false.\n"
    )
    user = (
        f"{(tool_facts or '').strip()}\n\n"
        f"Бриф:\n{review_brief(task_description)}\n\n"
        f"Критерии:\n{criteria_json}\n\n"
        f"Код:\n{code}\n"
    )
    try:
        raw = await llm.generate(system, user)
        checks = _parse_checks_json(raw, rubric)
        if checks:
            return checks
    except Exception:
        pass
    return _grade_heuristic(code=code, rubric=rubric)


def rubric_score_and_cap(checks: list[CriterionCheck]) -> tuple[int, int | None, list[str]]:
    if not checks:
        return 10, None, []
    total = len(checks)
    passed = sum(1 for item in checks if item.passed)
    ratio = passed / total
    score = max(1, min(10, 1 + round(9 * ratio)))

    required = [item for item in checks if item.required]
    required_failed = [item for item in required if not item.passed]
    reasons: list[str] = [f"критерии приёмки: {passed}/{total}"]
    cap: int | None = None
    if required_failed:
        fail_ratio = len(required_failed) / max(1, len(required))
        if fail_ratio >= 0.5:
            cap = min(score, 5)
            reasons.append("не закрыта большая часть обязательных критериев — потолок 5")
        else:
            cap = min(score, 7)
            reasons.append("есть проваленные обязательные критерии — потолок 7")
        for item in required_failed[:3]:
            reasons.append(f"не закрыто: {item.text}")
    return score, cap, reasons


def format_checks_for_feedback(checks: list[CriterionCheck]) -> str:
    if not checks:
        return ""
    lines = ["**Критерии приёмки**"]
    for item in checks:
        mark = "✓" if item.passed else "✗"
        note = f" — {item.note}" if item.note else ""
        lines.append(f"{mark} {item.text}{note}")
    return "\n".join(lines)


def _grade_heuristic(code: str, rubric: AcceptanceRubric) -> list[CriterionCheck]:
    lowered = code.lower()
    checks: list[CriterionCheck] = []
    for item in rubric.criteria:
        tokens = _keywords(item.text)
        hit = sum(1 for token in tokens if token in lowered)
        passed = hit >= max(1, len(tokens) // 2) if tokens else False
        note = "есть следы требования в коде" if passed else "по тексту кода требование не видно"
        checks.append(
            CriterionCheck(
                id=item.id,
                text=item.text,
                passed=passed,
                note=note,
                required=item.required,
            )
        )
    return checks


def _parse_rubric_json(raw: str) -> AcceptanceRubric | None:
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        return None
    items = data.get("criteria")
    if not isinstance(items, list):
        return None
    criteria: list[AcceptanceCriterion] = []
    for index, item in enumerate(items[:6], start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        cid = str(item.get("id") or f"c{index}").strip() or f"c{index}"
        required = bool(item.get("required", True))
        criteria.append(AcceptanceCriterion(id=cid, text=_clip(text, 160), required=required))
    return AcceptanceRubric(criteria=criteria) if criteria else None


def _parse_checks_json(raw: str, rubric: AcceptanceRubric) -> list[CriterionCheck]:
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        return []
    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list):
        return []
    by_id = {
        str(item.get("id")): item
        for item in raw_checks
        if isinstance(item, dict) and item.get("id") is not None
    }
    result: list[CriterionCheck] = []
    for criterion in rubric.criteria:
        item = by_id.get(criterion.id)
        if not isinstance(item, dict):
            result.append(
                CriterionCheck(
                    id=criterion.id,
                    text=criterion.text,
                    passed=False,
                    note="нет ответа по критерию",
                    required=criterion.required,
                )
            )
            continue
        note = _clip(str(item.get("note") or "").strip(), 140)
        line = _as_line(item.get("line"))
        result.append(
            CriterionCheck(
                id=criterion.id,
                text=criterion.text,
                passed=bool(item.get("passed")),
                note=note,
                required=criterion.required,
                line=line,
            )
        )
    return result


def _as_line(raw: object) -> int | None:
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 10_000 else None


def _extract_json_object(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _split_requirements(text: str) -> list[str]:
    parts = re.split(r"[\n;.]+", text)
    cleaned: list[str] = []
    for part in parts:
        chunk = " ".join(part.split()).strip(" -•\t")
        if len(chunk) < 12:
            continue
        if not _looks_like_requirement(chunk):
            continue
        cleaned.append(_clip(chunk, 160))
    if cleaned:
        return cleaned
    soft = []
    for part in re.split(r"[\n.]+", text):
        chunk = " ".join(part.split()).strip()
        if len(chunk) >= 20:
            soft.append(_clip(chunk, 160))
        if len(soft) >= 4:
            break
    return soft


def _looks_like_requirement(chunk: str) -> bool:
    lower = chunk.lower()
    markers = (
        "напиш",
        "сделай",
        "верн",
        "долж",
        "нужн",
        "не использ",
        "без ",
        "проверь",
        "добавь",
        "реализ",
        "обработ",
        "валид",
        "тест",
        "если ",
        "require",
        "must",
        "should",
        "return",
    )
    return any(marker in lower for marker in markers)


def _keywords(text: str) -> list[str]:
    stop = {
        "и",
        "или",
        "для",
        "при",
        "что",
        "это",
        "как",
        "если",
        "то",
        "на",
        "по",
        "из",
        "в",
        "с",
        "без",
        "не",
        "a",
        "the",
        "to",
        "of",
        "and",
    }
    tokens = re.findall(r"[a-zA-Zа-яА-Я_]{4,}", text.lower())
    return [token for token in tokens if token not in stop][:6]


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
