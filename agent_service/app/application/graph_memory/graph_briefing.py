import logging

from agent_service.app.application.graph_memory.consolidation import is_chronic
from agent_service.app.application.graph_memory.ontology import classify_skill
from agent_service.app.application.graph_memory.recipes import ReadIntent
from agent_service.app.application.interfaces.graph_memory import GraphMemoryInterface


MAX_LINES = 4
HEADER = "Память команды об этом студенте:"


async def graph_briefing(
        graph: GraphMemoryInterface | None,
        user_id: str | None,
        message: str,
        task_title: str = "",
        focus_skill: str = "",
        logger: logging.Logger | None = None,
) -> str:
    if graph is None or not graph.enabled or not user_id:
        return ""
    skill_ids = [item for item in (focus_skill, classify_skill(f"{task_title} {message}")) if item]
    intent = ReadIntent.TASK_CONTEXT if skill_ids else ReadIntent.CHAT_CONTEXT
    try:
        facts = await graph.facts_for(
            user_id=str(user_id),
            intent=intent,
            query=message,
            skill_ids=skill_ids,
        )
    except Exception:
        if logger is not None:
            logger.exception("graph_memory.briefing_failed user=%s", user_id)
        return ""
    if not facts:
        return ""

    lines: list[str] = [HEADER]
    for fact in facts[:MAX_LINES]:
        statement = (fact.statement or "").strip()
        if not statement:
            continue
        mark = f" (повторяется ×{fact.occurrences})" if is_chronic(fact) else ""
        lines.append(f"- {statement}{mark}")
    if len(lines) == 1:
        return ""
    lines.append(
        "Это память, а не условие задачи: упоминай её, только если она помогает ответу."
    )
    return "\n".join(lines)
