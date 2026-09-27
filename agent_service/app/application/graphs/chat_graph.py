from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from agent_service.app.application.graphs.state import ChatGraphRuntime, ChatState
from agent_service.app.application.graphs.tracing import traced_node
from agent_service.app.application.review.agent_path import AgentPath
from agent_service.app.application.team import member_by_id


CHAT_GRAPH_NODES = (
    "route",
    "solo_speak",
    "huddle_advisors",
    "huddle_speak",
    "process_eval",
    "finalize",
)


def compile_chat_graph(checkpointer: Any | None = None) -> Any:
    builder = StateGraph(ChatState, context_schema=ChatGraphRuntime)
    builder.add_node("route", traced_node("chat", "route", run_route_node))
    builder.add_node("solo_speak", traced_node("chat", "solo_speak", run_solo_speak_node))
    builder.add_node("huddle_advisors", traced_node("chat", "huddle_advisors", run_huddle_advisors_node))
    builder.add_node("huddle_speak", traced_node("chat", "huddle_speak", run_huddle_speak_node))
    builder.add_node("process_eval", traced_node("chat", "process_eval", run_process_eval_node))
    builder.add_node("finalize", traced_node("chat", "finalize", run_finalize_node))
    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        _after_route,
        {
            "solo_speak": "solo_speak",
            "huddle_advisors": "huddle_advisors",
        },
    )
    builder.add_edge("solo_speak", "process_eval")
    builder.add_edge("huddle_advisors", "huddle_speak")
    builder.add_edge("huddle_speak", "process_eval")
    builder.add_edge("process_eval", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def _after_route(state: ChatState) -> Literal["solo_speak", "huddle_advisors"]:
    if state.get("mode") == "huddle":
        return "huddle_advisors"
    return "solo_speak"


def _ctx(runtime: Runtime[ChatGraphRuntime]) -> ChatGraphRuntime:
    return runtime.context


def _path(state: ChatState) -> AgentPath:
    return state.get("path") or AgentPath()


async def run_route_node(state: ChatState, runtime: Runtime[ChatGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    user_context = state.get("user_context")
    solo_only = bool(user_context.get("solo_only")) if isinstance(user_context, dict) else False
    emma_session = (
        bool(str(user_context.get("emma_briefing") or "").strip())
        if isinstance(user_context, dict)
        else False
    )
    decision, path = await ctx.orchestrator.step_route(
        message=state["message"],
        trajectory_action=state.get("trajectory_action"),
        path=_path(state),
        solo_only=solo_only,
        emma_session=emma_session,
        trajectory_mentor=(
            str(user_context.get("trajectory_mentor") or "") or None
            if isinstance(user_context, dict)
            else None
        ),
    )
    return {
        "mode": decision.mode,
        "speaker_id": decision.speaker.id,
        "speaker_name": decision.speaker.name,
        "speaker_role": decision.speaker.role,
        "route_reason": decision.reason,
        "route_source": decision.source,
        "path": path,
    }


async def run_solo_speak_node(state: ChatState, runtime: Runtime[ChatGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    answer, path = await ctx.orchestrator.step_solo_speak(
        message=state["message"],
        chat_history=list(state.get("chat_history") or []),
        user_context=state.get("user_context"),
        speaker=member_by_id(str(state.get("speaker_id") or "john")),
        path=_path(state),
    )
    return {"answer": answer, "advisors": [], "path": path}


async def run_huddle_advisors_node(state: ChatState, runtime: Runtime[ChatGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    briefing, advisors, path = await ctx.orchestrator.step_huddle_advisors(
        message=state["message"],
        chat_history=list(state.get("chat_history") or []),
        user_context=state.get("user_context"),
        speaker=member_by_id(str(state.get("speaker_id") or "john")),
        path=_path(state),
    )
    return {"briefing": briefing, "advisors": advisors, "path": path}


async def run_huddle_speak_node(state: ChatState, runtime: Runtime[ChatGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    answer, path = await ctx.orchestrator.step_huddle_speak(
        message=state["message"],
        chat_history=list(state.get("chat_history") or []),
        user_context=state.get("user_context"),
        speaker=member_by_id(str(state.get("speaker_id") or "john")),
        briefing=str(state.get("briefing") or ""),
        path=_path(state),
    )
    return {"answer": answer, "path": path}


async def run_process_eval_node(state: ChatState, runtime: Runtime[ChatGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    path = ctx.orchestrator.step_process_eval(
        mode=str(state.get("mode") or "solo"),
        speaker_id=str(state.get("speaker_id") or ""),
        advisors=list(state.get("advisors") or []),
        answer=str(state.get("answer") or ""),
        path=_path(state),
    )
    return {"path": path}


async def run_finalize_node(state: ChatState, runtime: Runtime[ChatGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    result = ctx.orchestrator.step_finalize(
        answer=str(state.get("answer") or ""),
        speaker_id=str(state.get("speaker_id") or "john"),
        speaker_name=str(state.get("speaker_name") or ""),
        speaker_role=str(state.get("speaker_role") or ""),
        mode=str(state.get("mode") or "solo"),
        advisors=list(state.get("advisors") or []),
        path=_path(state),
    )
    return {"result": result}
