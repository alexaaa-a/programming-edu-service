import logging
from typing import Any

from agent_service.app.application.observability.llm_trace import (
    LlmTracer,
    clip_for_trace,
    get_noop_tracer,
)

_logger = logging.getLogger(__name__)

_TERMINAL_KEYS = ("review", "result")


def graph_has_checkpointer(graph: Any) -> bool:
    checkpointer = getattr(graph, "checkpointer", None)
    return checkpointer not in (None, False)


def draw_graph_mermaid(graph: Any) -> str:
    try:
        return str(graph.get_graph().draw_mermaid())
    except Exception:
        return ""


async def delete_graph_thread(graph: Any, thread_id: str | None) -> None:
    if not thread_id or not graph_has_checkpointer(graph):
        return
    checkpointer = getattr(graph, "checkpointer", None)
    delete = getattr(checkpointer, "adelete_thread", None)
    if delete is None:
        return
    await delete(thread_id)


def _terminal_values(snap: Any) -> dict[str, Any] | None:
    if bool(getattr(snap, "next", ())):
        return None
    values = getattr(snap, "values", None)
    if not isinstance(values, dict) or not values:
        return None
    if any(key in values and values[key] is not None for key in _TERMINAL_KEYS):
        return values
    return None


async def ainvoke_graph(
        graph: Any,
        state: dict[str, Any],
        context: Any,
        tracer: LlmTracer | None = None,
        thread_id: str | None = None,
        graph_name: str = "graph",
) -> dict[str, Any]:
    active = tracer or get_noop_tracer()
    mermaid = draw_graph_mermaid(graph)
    use_thread = bool(thread_id) and graph_has_checkpointer(graph)
    config = {"configurable": {"thread_id": thread_id}} if use_thread else None
    with active.observation(
        f"langgraph.{graph_name}",
        as_type="span",
        metadata={
            "graph": graph_name,
            "thread_id": thread_id or "",
            "mermaid": clip_for_trace(mermaid, max_chars=2500) if mermaid else "",
        },
    ) as obs:
        resumed = False
        reused_terminal = False
        if config is not None:
            try:
                snap = await graph.aget_state(config)
            except Exception:
                _logger.exception(
                    "langgraph.aget_state failed graph=%s thread_id=%s; refusing blind re-run",
                    graph_name,
                    thread_id,
                )
                raise
            terminal = _terminal_values(snap)
            if terminal is not None:
                reused_terminal = True
                out = terminal
            elif bool(getattr(snap, "next", ())):
                resumed = True
                out = await graph.ainvoke(None, config=config, context=context)
            else:
                out = await graph.ainvoke(state, config=config, context=context)
        else:
            out = await graph.ainvoke(state, context=context)
        obs.update(
            output={
                "resumed": resumed,
                "reused_terminal": reused_terminal,
                "keys": sorted(out.keys()) if isinstance(out, dict) else [],
            }
        )
        return out
