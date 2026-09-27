from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.tools.models import ToolFinding, ToolReport


async def load_past_reviews(
    memory: MemoryInterface,
    task_description: str,
    task_id: str | None,
    user_id: str | None = None,
) -> list[ToolFinding]:
    if not user_id or not task_id:
        return []
    query = (
        f"task_id={task_id}\nuser_id={user_id}\n"
        f"{task_description.strip() or 'прошлые ревью этой задачи'}"
    )
    docs = await memory.retrieve(query=query, k=4, types={"past_review"})
    docs = [
        d
        for d in docs
        if str((d.metadata or {}).get("type", "")) == "past_review"
        and str((d.metadata or {}).get("user_id", "")) == str(user_id)
        and str((d.metadata or {}).get("task_id", "")) == str(task_id)
    ]
    return _as_findings(docs, prefix="Прошлое ревью")


async def load_student_notes(
        memory: MemoryInterface,
        user_id: str | None,
        task_description: str,
) -> list[ToolFinding]:
    if not user_id:
        return []
    query = f"user_id={user_id}\n{task_description}".strip()
    docs = await memory.retrieve(query=query, k=4, types={"student_note"})
    docs = [
        d
        for d in docs
        if str((d.metadata or {}).get("type", "")) == "student_note"
        and str((d.metadata or {}).get("user_id", "")) == str(user_id)
    ]
    return _as_findings(docs, prefix="Профиль студента")


async def save_review_memory(
        memory: MemoryInterface,
        task_id: str | None,
        submission_id: str | None,
        score: int,
        feedback: str,
        suggestions: list[str],
        user_id: str | None = None,
) -> None:
    if not task_id and not submission_id:
        return
    if not user_id:
        return
    bits = [f"Скор {score}/10.", feedback.strip()]
    if suggestions:
        bits.append("Правки: " + "; ".join(suggestions[:4]))
    text = " ".join(p for p in bits if p)
    metadata: dict[str, str | int] = {
        "type": "past_review",
        "source": "review_pipeline",
        "writer": "review_orchestrator",
        "origin": "submission_review",
        "user_id": str(user_id),
    }
    if task_id:
        metadata["task_id"] = str(task_id)
    if submission_id:
        metadata["submission_id"] = str(submission_id)
        metadata["id"] = f"past_review_{submission_id}"
    await memory.save_document(text, metadata)
    previous = await load_student_notes(
        memory,
        user_id=user_id,
        task_description=feedback or task_id or "профиль",
    )
    facts = compress_student_facts(
        score=score,
        feedback=feedback,
        suggestions=suggestions,
        previous=[item.message for item in previous],
    )
    if not facts:
        return
    await memory.save_document(
        f"Студент {user_id}. Типичное: {facts}.",
        {
            "type": "student_note",
            "source": "review_pipeline",
            "writer": "review_orchestrator",
            "origin": "student_profile",
            "user_id": str(user_id),
            "id": f"student_{user_id}",
            **({"task_id": str(task_id)} if task_id else {}),
        },
    )


_FACT_HINTS: tuple[tuple[str, str], ...] = (
    ("голый except", "глотает ошибки голым except"),
    ("except", "плохо обрабатывает исключения"),
    ("синтаксис", "ломает синтаксис"),
    ("компил", "сдаёт код, который не компилируется"),
    ("тест", "слабые или падающие тесты"),
    ("мутаб", "мутабельный аргумент по умолчанию"),
    ("дефолт", "опасные значения по умолчанию"),
    ("валид", "слабая валидация входа"),
    ("eval", "использует eval/exec"),
    ("пуст", "оставляет пустые функции"),
    ("логическ", "ошибки в логике"),
    ("гранич", "не думает про крайние случаи"),
)


def compress_student_facts(
        score: int,
        feedback: str,
        suggestions: list[str],
        previous: list[str] | None = None,
) -> str:
    blob = f"{feedback} {' '.join(suggestions)}".lower()
    facts: list[str] = []
    for needle, fact in _FACT_HINTS:
        if needle in blob and fact not in facts:
            facts.append(fact)
        if len(facts) >= 2:
            break
    if len(facts) < 2:
        for suggestion in suggestions:
            clean = _trim(suggestion.strip().rstrip("."), 90)
            if clean and clean not in facts:
                facts.append(clean)
            if len(facts) >= 2:
                break
    if not facts and score <= 4:
        facts.append(f"слабые сдачи, скор {score}/10")
    for item in previous or []:
        extracted = _facts_from_note(item)
        for fact in extracted:
            if fact not in facts:
                facts.append(fact)
            if len(facts) >= 2:
                break
        if len(facts) >= 2:
            break
    return "; ".join(facts[:2])


def _facts_from_note(text: str) -> list[str]:
    marker = "типичное:"
    lower = text.lower()
    if marker not in lower:
        return []
    tail = text[lower.index(marker) + len(marker) :].strip()
    return [part.strip() for part in tail.split(";") if part.strip()]


def score_cap_from_report(report: ToolReport) -> int | None:
    if not report.syntax_ok or not report.compile_ok:
        return 2
    if report.tests_run and report.tests_passed is False:
        return 4
    error_count = sum(1 for f in report.findings if f.severity == "error")
    if error_count >= 2:
        return 5
    return None


def _as_findings(docs: list, prefix: str) -> list[ToolFinding]:
    from agent_service.app.application.memory.provenance import format_provenance

    findings: list[ToolFinding] = []
    for doc in docs[:3]:
        text = (doc.text or "").strip()
        if not text:
            continue
        provenance = format_provenance(doc.metadata)
        label = f"{prefix} [{provenance}]" if provenance else prefix
        findings.append(ToolFinding("memory", "info", f"{label}: {_trim(text, 260)}"))
    return findings


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
