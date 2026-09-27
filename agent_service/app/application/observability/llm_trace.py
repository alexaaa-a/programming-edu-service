from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Iterator, TypeVar

T = TypeVar("T")


ObservationType = str

_MAX_CHARS = 4_000
_MAX_LIST = 12


class Observation:
    def update(
            self,
            input: Any = None,
            output: Any = None,
            metadata: Mapping[str, Any] | None = None,
            model: str | None = None,
            model_parameters: Mapping[str, Any] | None = None,
            usage_details: Mapping[str, Any] | None = None,
            level: str | None = None,
            status_message: str | None = None,
            **kwargs: Any,
    ) -> None:
        return None

    def update_trace(
            self,
            name: str | None = None,
            user_id: str | None = None,
            session_id: str | None = None,
            tags: Sequence[str] | None = None,
            metadata: Mapping[str, Any] | None = None,
            input: Any = None,
            output: Any = None,
            **kwargs: Any,
    ) -> None:
        return None

    def score(
            self,
            name: str,
            value: float | int | bool,
            data_type: str = "NUMERIC",
            comment: str | None = None,
    ) -> None:
        return None


class LlmTracer:
    enabled: bool = False

    @contextmanager
    def observation(
            self,
            name: str,
            as_type: ObservationType = "span",
            input: Any = None,
            output: Any = None,
            metadata: Mapping[str, Any] | None = None,
            user_id: str | None = None,
            session_id: str | None = None,
            tags: Sequence[str] | None = None,
            model: str | None = None,
            model_parameters: Mapping[str, Any] | None = None,
            **kwargs: Any,
    ) -> Iterator[Observation]:
        yield Observation()

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


NOOP_TRACER = LlmTracer()


def get_noop_tracer() -> LlmTracer:
    return NOOP_TRACER


def clip_for_trace(value: Any, max_chars: int = _MAX_CHARS) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rsplit(" ", 1)[0].strip() + "…"
    if isinstance(value, Mapping):
        return {str(key): clip_for_trace(item, max_chars=max_chars) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        clipped = [clip_for_trace(item, max_chars=max_chars) for item in value[:_MAX_LIST]]
        extra = len(value) - _MAX_LIST
        if extra > 0:
            clipped.append(f"… +{extra} more")
        return clipped
    if isinstance(value, (int, float, bool)):
        return value
    return clip_for_trace(str(value), max_chars=max_chars)


def safe_metadata(data: Mapping[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[str(key)] = value if not isinstance(value, str) else value[:500]
        else:
            out[str(key)] = clip_for_trace(value, max_chars=400)
    return out


async def trace_async(
        tracer: LlmTracer | None,
        name: str,
        fn: Callable[[], Awaitable[T]],
        as_type: ObservationType = "span",
        input: Any = None,
        metadata: Mapping[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: Sequence[str] | None = None,
        model: str | None = None,
        model_parameters: Mapping[str, Any] | None = None,
        output_from: Callable[[T], Any] | None = None,
        metadata_from: Callable[[T], Mapping[str, Any] | None] | None = None,
        scores_from: Callable[[T], Sequence[tuple[str, float | int | bool, dict[str, Any]]]] | None = None,
        flush: bool = False,
) -> T:
    active = tracer or NOOP_TRACER
    with active.observation(
        name,
        as_type=as_type,
        input=input,
        metadata=metadata,
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        model=model,
        model_parameters=model_parameters,
    ) as obs:
        result = await fn()
        extra_meta = metadata_from(result) if metadata_from is not None else None
        output = output_from(result) if output_from is not None else None
        obs.update(output=output, metadata=extra_meta)
        if scores_from is not None:
            for score_name, value, extra in scores_from(result):
                obs.score(
                    score_name,
                    value,
                    data_type=str(extra.get("data_type") or "NUMERIC"),
                    comment=extra.get("comment") if isinstance(extra.get("comment"), str) else None,
                )
        if flush:
            active.flush()
        return result
