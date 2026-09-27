from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from agent_service.app.application.graphs.state import ReviewGraphRuntime, ReviewState
from agent_service.app.application.graphs.tracing import traced_node
from agent_service.app.application.review.agent_path import AgentPath

REVIEW_GRAPH_NODES = (
    "tools",
    "acceptance_rubric",
    "reviewer_bug",
    "grade_rubric",
    "adversarial",
    "scorecard_draft",
    "mentor_plan",
    "mentor_single",
    "mentor_multi",
    "process_eval",
    "finalize",
)


def compile_review_graph(checkpointer: Any | None = None) -> Any:
    builder = StateGraph(ReviewState, context_schema=ReviewGraphRuntime)
    builder.add_node("tools", traced_node("review", "tools", run_tools_node))
    builder.add_node("acceptance_rubric", traced_node("review", "acceptance_rubric", run_acceptance_node))
    builder.add_node("reviewer_bug", traced_node("review", "reviewer_bug", run_reviewer_bug_node))
    builder.add_node("grade_rubric", traced_node("review", "grade_rubric", run_grade_node))
    builder.add_node("adversarial", traced_node("review", "adversarial", run_adversarial_node))
    builder.add_node("scorecard_draft", traced_node("review", "scorecard_draft", run_scorecard_draft_node))
    builder.add_node("mentor_plan", traced_node("review", "mentor_plan", run_mentor_plan_node))
    builder.add_node("mentor_single", traced_node("review", "mentor_single", run_mentor_single_node))
    builder.add_node("mentor_multi", traced_node("review", "mentor_multi", run_mentor_multi_node))
    builder.add_node("process_eval", traced_node("review", "process_eval", run_process_eval_node))
    builder.add_node("finalize", traced_node("review", "finalize", run_finalize_node))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", "acceptance_rubric")
    builder.add_edge("acceptance_rubric", "reviewer_bug")
    builder.add_edge("reviewer_bug", "grade_rubric")
    builder.add_edge("grade_rubric", "adversarial")
    builder.add_edge("adversarial", "scorecard_draft")
    builder.add_edge("scorecard_draft", "mentor_plan")
    builder.add_conditional_edges(
        "mentor_plan",
        _after_mentor_plan,
        {
            "mentor_single": "mentor_single",
            "mentor_multi": "mentor_multi",
        },
    )
    builder.add_edge("mentor_single", "process_eval")
    builder.add_edge("mentor_multi", "process_eval")
    builder.add_edge("process_eval", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def compile_review_spike_graph(checkpointer: Any | None = None) -> Any:
    return compile_review_graph(checkpointer=checkpointer)


def _after_mentor_plan(state: ReviewState) -> Literal["mentor_single", "mentor_multi"]:
    if int(state.get("n_drafts") or 1) > 1:
        return "mentor_multi"
    return "mentor_single"


def _path(state: ReviewState) -> AgentPath:
    return state.get("path") or AgentPath()


def _ctx(runtime: Runtime[ReviewGraphRuntime]) -> ReviewGraphRuntime:
    return runtime.context


async def run_tools_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    report, tool_facts, path = await ctx.orchestrator.step_tools(
        code=state["code"],
        task_description=state["task_description"],
        task_id=state.get("task_id"),
        user_id=state.get("user_id"),
        attempt=state.get("attempt"),
        previous_feedback=state.get("previous_feedback"),
        path=_path(state),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"tool_report": report, "tool_facts": tool_facts, "path": path}


async def run_acceptance_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    rubric, tool_facts, path = await ctx.orchestrator.step_acceptance_rubric(
        task_description=state["task_description"],
        tool_facts=str(state.get("tool_facts") or ""),
        path=_path(state),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"rubric": rubric, "tool_facts": tool_facts, "path": path}


async def run_reviewer_bug_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    reviewer_review, bug_review, path = await ctx.orchestrator.step_reviewer_bug(
        code=state["code"],
        task_description=state["task_description"],
        tool_facts=str(state.get("tool_facts") or ""),
        path=_path(state),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"reviewer_review": reviewer_review, "bug_review": bug_review, "path": path}


async def run_grade_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    checks, path = await ctx.orchestrator.step_grade_rubric(
        code=state["code"],
        task_description=state["task_description"],
        tool_facts=str(state.get("tool_facts") or ""),
        rubric=state.get("rubric"),
        path=_path(state),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"checks": checks, "path": path}


async def run_adversarial_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    challenge, path = await ctx.orchestrator.step_adversarial(
        code=state["code"],
        task_description=state["task_description"],
        tool_facts=str(state.get("tool_facts") or ""),
        reviewer_review=state["reviewer_review"],
        bug_review=state["bug_review"],
        checks=list(state.get("checks") or []),
        report=state.get("tool_report"),
        path=_path(state),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"challenge": challenge, "path": path}


async def run_scorecard_draft_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    draft_card = ctx.orchestrator.step_scorecard_draft(
        reviewer_review=state["reviewer_review"],
        bug_review=state["bug_review"],
        report=state.get("tool_report"),
        checks=list(state.get("checks") or []),
        challenge=state.get("challenge"),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"draft_card": draft_card}


async def run_mentor_plan_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    n_drafts = ctx.orchestrator.step_mentor_plan(
        draft_card=state.get("draft_card"),
        checks=list(state.get("checks") or []),
        challenge=state.get("challenge"),
        report=state.get("tool_report"),
    )
    return {"n_drafts": n_drafts}


async def _run_mentor(
        state: ReviewState,
        runtime: Runtime[ReviewGraphRuntime],
        n_drafts: int,
) -> dict[str, Any]:
    ctx = _ctx(runtime)
    mentor_feedback, mentor_ok, path = await ctx.orchestrator.step_mentor(
        code=state["code"],
        tool_facts=str(state.get("tool_facts") or ""),
        reviewer_review=state["reviewer_review"],
        bug_review=state["bug_review"],
        report=state.get("tool_report"),
        checks=list(state.get("checks") or []),
        challenge=state.get("challenge"),
        draft_card=state["draft_card"],
        path=_path(state),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
        n_drafts=n_drafts,
    )
    return {"mentor_feedback": mentor_feedback, "mentor_ok": mentor_ok, "path": path}


async def run_mentor_single_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    return await _run_mentor(state, runtime, n_drafts=1)


async def run_mentor_multi_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    return await _run_mentor(state, runtime, n_drafts=max(int(state.get("n_drafts") or 2), 2))


async def run_process_eval_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    path_verdict, path = ctx.orchestrator.step_process_eval(
        path=_path(state),
        report=state.get("tool_report"),
        mentor_feedback=str(state.get("mentor_feedback") or ""),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"path_verdict": path_verdict, "path": path}


async def run_finalize_node(state: ReviewState, runtime: Runtime[ReviewGraphRuntime]) -> dict[str, Any]:
    ctx = _ctx(runtime)
    review = await ctx.orchestrator.step_finalize(
        reviewer_review=state["reviewer_review"],
        bug_review=state["bug_review"],
        report=state.get("tool_report"),
        checks=list(state.get("checks") or []),
        challenge=state.get("challenge"),
        path=_path(state),
        path_verdict=state["path_verdict"],
        mentor_feedback=str(state.get("mentor_feedback") or ""),
        task_id=state.get("task_id"),
        submission_id=state.get("submission_id"),
        user_id=state.get("user_id"),
        logger=ctx.logger,
        trace_id=ctx.trace_id,
    )
    return {"review": review}
