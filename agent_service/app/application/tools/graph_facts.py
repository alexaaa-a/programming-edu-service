import logging
from typing import Sequence

from agent_service.app.application.graph_memory.consolidation import is_chronic
from agent_service.app.application.graph_memory.facts import StoredFact
from agent_service.app.application.graph_memory.ontology import classify_skill
from agent_service.app.application.graph_memory.recipes import ReadIntent
from agent_service.app.application.interfaces.graph_memory import GraphMemoryInterface
from agent_service.app.application.tools.models import ToolFinding


MAX_FINDINGS = 4

SOURCE_LABELS: dict[str, str] = {
    "hidden_tests": "подтверждено прогоном тестов",
    "review": "по ревью",
    "trajectory": "по модели знаний",
    "chat": "со слов студента",
}


async def load_graph_facts(
        graph: GraphMemoryInterface | None,
        user_id: str | None,
        task_description: str = "",
        task_id: str | None = None,
        logger: logging.Logger | None = None,
) -> list[ToolFinding]:
    if graph is None or not graph.enabled or not user_id:
        return []
    skill_ids = skills_of_task(task_description)
    intent = ReadIntent.TASK_CONTEXT if skill_ids else ReadIntent.STUDENT_NOW
    query = _query_for(task_description, task_id)
    try:
        facts = await graph.facts_for(
            user_id=str(user_id),
            intent=intent,
            query=query,
            skill_ids=skill_ids,
        )
    except Exception:
        if logger is not None:
            logger.exception("tools.graph_facts.failed user=%s", user_id)
        return []
    return as_findings(facts)


def as_findings(facts: Sequence[StoredFact]) -> list[ToolFinding]:
    out: list[ToolFinding] = []
    for fact in facts[:MAX_FINDINGS]:
        statement = (fact.statement or "").strip()
        if not statement:
            continue
        severity = "warn" if is_chronic(fact) else "info"
        out.append(ToolFinding("graph_memory", severity, f"Память команды [{_marks(fact)}]: {statement}"))
    return out


def skills_of_task(task_description: str) -> list[str]:
    skill_id = classify_skill(task_description or "")
    return [skill_id] if skill_id else []


def _marks(fact: StoredFact) -> str:
    marks: list[str] = []
    if is_chronic(fact):
        marks.append(f"повторяется ×{fact.occurrences}")
    elif fact.occurrences > 1:
        marks.append(f"×{fact.occurrences}")
    marks.append(SOURCE_LABELS.get(fact.source.value, fact.source.value))
    days = int(fact.age_days())
    if days >= 1:
        marks.append(f"{days} дн. назад")
    return ", ".join(marks)


def _query_for(task_description: str, task_id: str | None) -> str:
    text = " ".join((task_description or "").split())[:400]
    if text:
        return text
    return f"recurring problems of this student on task {task_id or 'unknown'}"
