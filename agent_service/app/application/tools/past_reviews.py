from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.dto.student_profile import StudentProfile
from agent_service.app.application.interfaces import MemoryInterface, StudentProfileRepository
from agent_service.app.application.memory.provenance import (
    compress_memory_text,
    is_fresh,
    validate_memory_text,
)
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
        profiles: StudentProfileRepository | None,
        user_id: str | None,
) -> list[ToolFinding]:
    if not user_id or profiles is None:
        return []
    profile = await _fresh_profile(profiles, str(user_id))
    if profile is None:
        return []
    doc = RetrievedDocument(
        text=_profile_text(profile.user_id, profile.facts),
        metadata=_profile_metadata(profile),
    )
    return _as_findings([doc], prefix="Профиль студента")


async def save_review_memory(
        memory: MemoryInterface,
        task_id: str | None,
        submission_id: str | None,
        score: int,
        feedback: str,
        suggestions: list[str],
        user_id: str | None = None,
        profiles: StudentProfileRepository | None = None,
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
    if profiles is None:
        return
    key = str(user_id)
    existing = await _fresh_profile(profiles, key)
    facts = compress_student_facts(
        score=score,
        feedback=feedback,
        suggestions=suggestions,
        previous=existing.facts if existing is not None else None,
    )
    facts = [item for item in (compress_memory_text(f, "student_note") for f in facts) if item]
    if not facts:
        return
    ok, _reason = validate_memory_text(
        _profile_text(key, facts),
        doc_type="student_note",
        metadata={"user_id": key},
    )
    if not ok:
        return
    await profiles.save(key, facts, task_id=str(task_id) if task_id else None)


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
) -> list[str]:
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
    for fact in previous or []:
        if fact not in facts:
            facts.append(fact)
        if len(facts) >= 2:
            break
    return facts[:2]


async def _fresh_profile(
        profiles: StudentProfileRepository,
        user_id: str,
) -> StudentProfile | None:
    profile = await profiles.get(user_id)
    if profile is None or not profile.facts:
        return None
    if not is_fresh(_profile_metadata(profile)):
        return None
    return profile


def _profile_text(user_id: str, facts: list[str]) -> str:
    return f"Студент {user_id}. Типичное: {'; '.join(facts)}."


def _profile_metadata(profile: StudentProfile) -> dict[str, str]:
    meta: dict[str, str] = {
        "type": "student_note",
        "source": "review_pipeline",
        "writer": "review_orchestrator",
        "origin": "student_profile",
        "user_id": profile.user_id,
    }
    if profile.updated_at is not None:
        meta["saved_at"] = profile.updated_at.isoformat()
    if profile.last_task_id:
        meta["task_id"] = profile.last_task_id
    return meta


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
