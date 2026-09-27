import contextvars
import uuid
from dataclasses import dataclass


_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> contextvars.Token[str | None]:
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    _trace_id_var.reset(token)


def ensure_trace_id() -> str:
    trace_id = get_trace_id()
    if trace_id:
        return trace_id
    trace_id = uuid.uuid4().hex
    set_trace_id(trace_id)
    return trace_id


@dataclass(frozen=True, slots=True)
class Trace:
    trace_id: str
