import json
import re
from dataclasses import dataclass
from typing import Literal

from agent_service.app.application.team import (
    EMMA,
    JOHN,
    MIKE,
    SARA,
    TEAM_BY_ID,
    TEAM_MEMBERS,
    TeamMember,
    member_by_id,
)


ChatMode = Literal["solo", "huddle"]


@dataclass(frozen=True, slots=True)
class RouteDecision:
    mode: ChatMode
    speaker: TeamMember
    reason: str
    source: str


_MENTION_MAP: list[tuple[re.Pattern[str], TeamMember]] = [
    (re.compile(r"@?\bсара\b", re.IGNORECASE), TEAM_BY_ID["sara"]),
    (re.compile(r"@?\bsara\b", re.IGNORECASE), TEAM_BY_ID["sara"]),
    (re.compile(r"@?\bмайк\b", re.IGNORECASE), TEAM_BY_ID["mike"]),
    (re.compile(r"@?\bмайкл\b", re.IGNORECASE), TEAM_BY_ID["mike"]),
    (re.compile(r"@?\bmike\b", re.IGNORECASE), TEAM_BY_ID["mike"]),
    (re.compile(r"@?\bэмма\b", re.IGNORECASE), TEAM_BY_ID["emma"]),
    (re.compile(r"@?\bemma\b", re.IGNORECASE), EMMA),
    (re.compile(r"@?\bджон\b", re.IGNORECASE), JOHN),
    (re.compile(r"@?\bjohn\b", re.IGNORECASE), JOHN),
]

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sara": (
        "требован",
        "срок",
        "приоритет",
        "бриф",
        "критер",
        "dod",
        "приёмк",
        "приемк",
        "скоуп",
        "scope",
        "заказчик",
    ),
    "mike": (
        "данн",
        "метрик",
        "анализ",
        "sql",
        "схем",
        "статисти",
        "выборк",
        "логирован",
        "аналитик",
    ),
    "emma": (
        "баг",
        "ошиб",
        "тест",
        "qa",
        "падает",
        "edge",
        "регресс",
        "слом",
        "валидац",
        "падени",
    ),
    "john": (
        "архитект",
        "рефактор",
        "api",
        "модул",
        "структур",
        "паттерн",
        "слой",
        "интерфейс",
        "как лучше",
        "как правильно",
    ),
}


def detect_mention(message: str) -> TeamMember | None:
    for pattern, member in _MENTION_MAP:
        if pattern.search(message):
            return member
    return None


def detect_domains(message: str) -> set[str]:
    q = message.lower()
    found: set[str] = set()
    for member_id, words in _DOMAIN_KEYWORDS.items():
        if any(word in q for word in words):
            found.add(member_id)
    return found


def route_without_llm(
        message: str,
        trajectory_action: str | None = None,
        trajectory_mentor: str | None = None,
) -> RouteDecision | None:
    mentioned = detect_mention(message)
    if mentioned is not None:
        return RouteDecision(
            mode="solo",
            speaker=mentioned,
            reason="пользователь позвал по имени",
            source="mention",
        )

    domains = detect_domains(message)
    if len(domains) >= 2:
        return RouteDecision(
            mode="huddle",
            speaker=JOHN,
            reason="вопрос затрагивает несколько ролей",
            source="keywords",
        )
    if len(domains) == 1:
        member_id = next(iter(domains))
        return RouteDecision(
            mode="solo",
            speaker=member_by_id(member_id),
            reason=f"тема ближе к роли {member_id}",
            source="keywords",
        )
    if (trajectory_action or "").strip() == "chat":
        mentor = (trajectory_mentor or "").strip().lower()
        if mentor in TEAM_BY_ID:
            return RouteDecision(
                mode="solo",
                speaker=TEAM_BY_ID[mentor],
                reason="траектория: разобрать пробел с профильным участником",
                source="trajectory",
            )
        return RouteDecision(
            mode="solo",
            speaker=SARA,
            reason="траектория: разобрать замечания",
            source="trajectory",
        )
    return None


def parse_route_json(raw: str) -> RouteDecision | None:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned.removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None

    speaker_id = str(data.get("speaker", "john")).strip().lower()
    if speaker_id not in TEAM_BY_ID:
        speaker_id = "john"
    mode_raw = str(data.get("mode", "solo")).strip().lower()
    mode: ChatMode = "huddle" if mode_raw == "huddle" else "solo"
    return RouteDecision(
        mode=mode,
        speaker=TEAM_BY_ID[speaker_id],
        reason=str(data.get("reason", "классификация модели")),
        source="llm",
    )


def huddle_advisors(message: str, speaker: TeamMember) -> list[TeamMember]:
    advisors = [EMMA, SARA]
    if "mike" in detect_domains(message):
        advisors.append(MIKE)
    return [member for member in advisors if member.id != speaker.id]


def emma_session_route() -> RouteDecision:
    return RouteDecision(
        mode="solo",
        speaker=EMMA,
        reason="сессия Эммы",
        source="purchase",
    )


def limit_to_one_speaker(decision: RouteDecision) -> RouteDecision:
    if decision.mode == "solo":
        return decision
    return RouteDecision(
        mode="solo",
        speaker=decision.speaker,
        reason="один спикер за ход",
        source=decision.source,
    )


def default_route() -> RouteDecision:
    return RouteDecision(
        mode="solo",
        speaker=JOHN,
        reason="нет явной темы — отвечает тимлид",
        source="default",
    )


def route_system_prompt() -> str:
    roster = ", ".join(f"{m.id}={m.name} ({m.role})" for m in TEAM_MEMBERS)
    return (
        "Ты маршрутизатор командного чата. Не отвечай пользователю.\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"mode":"solo"|"huddle","speaker":"sara"|"mike"|"emma"|"john","reason":"<коротко>"}\n'
        f"Роли: {roster}.\n"
        "solo — один человек закрывает вопрос.\n"
        "huddle — несколько ролей: Эмма (риски) + Сара (бриф), Майк если данные/метрики, итог обычно Джон.\n"
        "speaker — кто пишет итоговый ответ пользователю. Для huddle обычно john.\n"
        "Эмма: баги, тесты, падения. Сара: бриф, срок, приоритет. "
        "Майк: данные и метрики. Джон: архитектура, API, как делать.\n"
    )
