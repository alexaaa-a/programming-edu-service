from collections.abc import Awaitable, Callable
from typing import Any

from agent_service.app.application.observability.llm_trace import get_noop_tracer

NodeFn = Callable[..., Awaitable[dict[str, Any]]]


def traced_node(graph_name: str, name: str, fn: NodeFn) -> NodeFn:
    async def wrapped(state: Any, runtime: Any) -> dict[str, Any]:
        ctx = getattr(runtime, "context", None)
        tracer = getattr(ctx, "tracer", None) or get_noop_tracer()
        trace_id = getattr(ctx, "trace_id", "") or ""
        with tracer.observation(
            name,
            as_type="span",
            metadata={"graph": graph_name, "node": name, "trace_id": trace_id},
        ) as obs:
            result = await fn(state, runtime)
            if isinstance(result, dict):
                obs.update(output={"keys": sorted(result.keys())})
            return result

    wrapped.__name__ = name
    wrapped.__qualname__ = name
    return wrapped
