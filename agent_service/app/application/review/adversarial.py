import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


SEVERITIES = ("low", "medium", "high")


@dataclass(frozen=True, slots=True)
class ChallengeVerdict:
    agrees: bool = True
    severity: str = "low"
    score_cap: int | None = None
    challenges: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    feedback: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def has_objections(self) -> bool:
        return (not self.agrees) or bool(self.challenges) or bool(self.missed)


def parse_challenge_verdict(raw: str) -> ChallengeVerdict:
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        raise ValueError("Challenge JSON is not an object")
    challenges = _string_list(data.get("challenges"))
    missed = _string_list(data.get("missed"))
    severity = str(data.get("severity") or "low").strip().lower()
    if severity not in SEVERITIES:
        severity = "medium" if challenges or missed else "low"
    score_cap = _optional_score(data.get("score_cap"))
    agrees = bool(data.get("agrees", not (challenges or missed)))
    if challenges or missed:
        agrees = False
    feedback = _clip(str(data.get("feedback") or "").strip(), 320)
    return ChallengeVerdict(
        agrees=agrees,
        severity=severity,
        score_cap=score_cap,
        challenges=challenges[:6],
        missed=missed[:6],
        feedback=feedback,
    )


def heuristic_challenge(
        team_task_score: int,
        team_reliability_score: int,
        tool_findings_errors: int = 0,
        syntax_ok: bool = True,
        compile_ok: bool = True,
        tests_failed: bool = False,
) -> ChallengeVerdict:
    challenges: list[str] = []
    missed: list[str] = []
    severity = "low"
    score_cap: int | None = None
    team_min = min(team_task_score, team_reliability_score)

    if not syntax_ok or not compile_ok:
        if team_min >= 4:
            challenges.append("Команда завысила оценку при сломанном синтаксисе/компиляции")
            score_cap = 2
            severity = "high"
        missed.append("Синтаксис или компиляция не проходят — это блокер")
    elif tests_failed and team_min >= 6:
        challenges.append("Тесты упали, а оценка команды слишком высокая")
        score_cap = 4
        severity = "high"
        missed.append("Падение тестов в песочнице")
    elif tool_findings_errors >= 2 and team_min >= 7:
        challenges.append("Несколько error от инструментов при высокой оценке команды")
        score_cap = 5
        severity = "medium"
        missed.append("Жёсткие замечания инструментов не отражены в балле")
    elif team_task_score >= 9 and team_reliability_score <= 5:
        challenges.append("Ревьюер и QA сильно разошлись — итог нельзя тянуть к верхней оценке")
        score_cap = max(team_reliability_score + 1, 5)
        severity = "medium"

    agrees = not challenges and not missed
    feedback = (
        "Независимая проверка не согласна с завышенной оценкой команды."
        if not agrees
        else "Независимая проверка не нашла существенных возражений."
    )
    return ChallengeVerdict(
        agrees=agrees,
        severity=severity,
        score_cap=score_cap,
        challenges=challenges,
        missed=missed,
        feedback=feedback,
    )


def adversarial_cap_and_reasons(verdict: ChallengeVerdict | None) -> tuple[int | None, list[str]]:
    if verdict is None or not verdict.has_objections:
        return None, []
    reasons: list[str] = ["состязательная проверка не согласна с командой"]
    cap = verdict.score_cap
    if cap is None:
        if verdict.severity == "high":
            cap = 5
            reasons.append("серьёзные возражения — потолок 5")
        elif verdict.severity == "medium":
            cap = 7
            reasons.append("есть возражения средней силы — потолок 7")
        else:
            reasons.append("мягкие возражения без жёсткого потолка")
    else:
        reasons.append(f"потолок состязательной проверки {cap}")
    for item in (verdict.challenges + verdict.missed)[:3]:
        reasons.append(f"возражение: {item}")
    return cap, reasons


def format_challenges_for_feedback(verdict: ChallengeVerdict | None) -> str:
    if verdict is None or not verdict.has_objections:
        return ""
    lines = ["**Независимая проверка**"]
    if verdict.feedback:
        lines.append(verdict.feedback)
    for item in verdict.challenges:
        lines.append(f"✗ {item}")
    for item in verdict.missed:
        if item in verdict.challenges:
            continue
        lines.append(f"✗ упущено: {item}")
    return "\n".join(lines)


def challenge_suggestions(verdict: ChallengeVerdict | None) -> list[str]:
    if verdict is None:
        return []
    items: list[str] = []
    for text in verdict.challenges + verdict.missed:
        tip = _clip(text, 140)
        if tip and tip not in items:
            items.append(tip)
        if len(items) >= 4:
            break
    return items


def _string_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if not isinstance(raw, list):
        text = _clip(str(raw).strip(), 160)
        return [text] if text else []
    out: list[str] = []
    for item in raw:
        text = _clip(str(item).strip(), 160)
        if text:
            out.append(text)
    return out


def _optional_score(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(1, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return None


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


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
