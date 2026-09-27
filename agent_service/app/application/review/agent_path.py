import re
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class PathStep:
    kind: str
    name: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class AgentPath:
    steps: list[PathStep] = field(default_factory=list)

    def record(
            self,
            name: str,
            kind: str = "step",
            status: str = "ok",
            detail: str = "",
    ) -> None:
        self.steps.append(
            PathStep(
                kind=kind,
                name=name,
                status=status,
                detail=(detail or "")[:240],
            )
        )

    def has(self, name: str) -> bool:
        return any(step.name == name for step in self.steps)

    def status_of(self, name: str) -> str | None:
        for step in reversed(self.steps):
            if step.name == name:
                return step.status
        return None

    def names(self) -> list[str]:
        return [step.name for step in self.steps]

    def as_dict(self) -> dict[str, object]:
        return {"steps": [step.as_dict() for step in self.steps]}

    def as_prompt_block(self) -> str:
        if not self.steps:
            return ""
        lines = ["Путь агентов (process trace):"]
        for step in self.steps:
            suffix = f" — {step.detail}" if step.detail else ""
            lines.append(f"- [{step.kind}/{step.status}] {step.name}{suffix}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PathVerdict:
    score: int
    cap: int | None = None
    violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations and self.cap is None

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "cap": self.cap,
            "violations": list(self.violations),
            "notes": list(self.notes),
            "ok": self.ok,
        }


REQUIRED_REVIEW_STEPS = (
    "tools",
    "acceptance_rubric",
    "reviewer",
    "bug",
    "grade_rubric",
    "adversarial",
    "mentor",
)


def evaluate_review_path(
        path: AgentPath,
        language: str | None = None,
        tools_ran: bool = False,
        syntax_checked: bool = False,
        compile_checked: bool = False,
        sandbox_eligible: bool = False,
        mentor_feedback: str = "",
) -> PathVerdict:
    violations: list[str] = []
    notes: list[str] = []
    score = 10

    for name in REQUIRED_REVIEW_STEPS:
        status = path.status_of(name)
        if status is None:
            violations.append(f"шаг «{name}» не выполнялся")
            score -= 2
        elif status == "error":
            violations.append(f"шаг «{name}» завершился ошибкой")
            score -= 2
        elif status == "skip":
            notes.append(f"шаг «{name}» пропущен")
            score -= 1

    supported = (language or "").lower() in {"python", "javascript"}
    if supported:
        if not tools_ran:
            violations.append("инструменты не запускались для поддерживаемого языка")
            score -= 3
        elif not syntax_checked:
            violations.append("static-анализ не отработал")
            score -= 2
        if sandbox_eligible and not compile_checked:
            # compile_checked means we attempted compile/sandbox path
            violations.append("песочница/компиляция обойдены")
            score -= 2
    else:
        notes.append("язык вне static/sandbox — инструменты намеренно ограничены")

    dump = mentor_leaked_solution(mentor_feedback)
    if dump:
        violations.append(dump)
        score -= 3

    score = max(1, min(10, score))
    cap: int | None = None
    if any("песочниц" in item or "инструменты не запускались" in item for item in violations):
        cap = min(score, 6)
    if any("готовое решение" in item or "полный код" in item for item in violations):
        cap = min(cap if cap is not None else score, 5)
    if len(violations) >= 3:
        cap = min(cap if cap is not None else score, 5)

    return PathVerdict(score=score, cap=cap, violations=violations, notes=notes)


def evaluate_chat_path(
        mode: str,
        speaker_id: str,
        advisors: list[str] | None = None,
        answer: str = "",
        expected_speaker: str | None = None,
        expected_mode: str | None = None,
) -> PathVerdict:
    violations: list[str] = []
    notes: list[str] = []
    score = 10
    advisors = advisors or []

    if not speaker_id:
        violations.append("спикер не выбран")
        score -= 3
    if expected_speaker and speaker_id != expected_speaker:
        violations.append(f"ожидался спикер {expected_speaker}, вызван {speaker_id}")
        score -= 2
    if expected_mode and mode != expected_mode:
        violations.append(f"ожидался режим {expected_mode}, получен {mode}")
        score -= 2
    if mode == "huddle" and not advisors:
        violations.append("huddle без советников — путь команды пустой")
        score -= 3
    if mode == "solo" and advisors:
        notes.append("solo, но советники всё же вызывались")
    if mentor_leaked_solution(answer):
        violations.append("ответ содержит готовое решение целиком")
        score -= 3

    score = max(1, min(10, score))
    cap = 5 if any("готовое решение" in item for item in violations) else None
    if mode == "huddle" and not advisors:
        cap = min(cap if cap is not None else 10, 6)
    return PathVerdict(score=score, cap=cap, violations=violations, notes=notes)


def path_cap_and_reasons(verdict: PathVerdict | None) -> tuple[int | None, list[str]]:
    if verdict is None:
        return None, []
    reasons: list[str] = [f"качество пути агентов: {verdict.score}/10"]
    reasons.extend(f"процесс: {item}" for item in verdict.violations[:4])
    reasons.extend(f"процесс: {item}" for item in verdict.notes[:2])
    return verdict.cap, reasons


def format_path_for_feedback(path: AgentPath | None, verdict: PathVerdict | None = None) -> str:
    if path is None or not path.steps:
        return ""
    lines = ["**Путь проверки**"]
    for step in path.steps:
        mark = {
            "ok": "✓",
            "warn": "!",
            "skip": "·",
            "error": "✗",
        }.get(step.status, "·")
        detail = f" — {step.detail}" if step.detail else ""
        lines.append(f"{mark} {step.name}{detail}")
    if verdict and verdict.violations:
        lines.append("Замечания по процессу:")
        for item in verdict.violations[:4]:
            lines.append(f"✗ {item}")
    return "\n".join(lines)


def mentor_leaked_solution(text: str) -> str | None:
    raw = text or ""
    fences = re.findall(r"```(?:\w+)?\n([\s\S]*?)```", raw)
    for block in fences:
        if _looks_like_full_solution(block):
            return "ментор выдал готовое решение целиком (блок кода)"
    if _looks_like_full_solution(raw) and raw.count("\n") >= 8:
        return "ментор выдал полный код решения без учебной дозировки"
    return None


def _looks_like_full_solution(text: str) -> bool:
    lowered = text.lower()
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 6:
        return False
    def_hits = len(re.findall(r"^\s*(def|class|function|const|let)\b", text, re.M))
    return_hits = lowered.count("return ")
    has_tests = "def test_" in lowered or "assert " in lowered
    if def_hits >= 2 and (return_hits >= 1 or has_tests) and len(lines) >= 6:
        return True
    if has_tests and def_hits >= 1 and len(lines) >= 8:
        return True
    return False
