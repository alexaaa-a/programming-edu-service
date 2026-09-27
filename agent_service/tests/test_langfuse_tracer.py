import asyncio

from agent_service.app.application.observability.llm_trace import (
    LlmTracer,
    Observation,
    clip_for_trace,
    get_noop_tracer,
    trace_async,
)
from agent_service.app.config import LangfuseSettings
from agent_service.app.infrastructure.observability.langfuse_tracer import build_llm_tracer


class RecordingTracer(LlmTracer):
    enabled = True

    def __init__(self) -> None:
        self.names: list[str] = []
        self.types: list[str] = []
        self.flushed = 0
        self.scores: list[tuple[str, float | int | bool]] = []
        self.last_input = None
        self.last_output = None

    def observation(self, name, *, as_type="span", input=None, **kwargs):
        tracer = self

        class _CM:
            def __enter__(self):
                tracer.names.append(name)
                tracer.types.append(as_type)
                tracer.last_input = input
                return _RecordingObservation(tracer)

            def __exit__(self, exc_type, exc, tb):
                return False

        return _CM()

    def flush(self) -> None:
        self.flushed += 1


class _RecordingObservation(Observation):
    def __init__(self, tracer: RecordingTracer) -> None:
        self._tracer = tracer

    def update(self, output=None, **kwargs) -> None:
        if output is not None:
            self._tracer.last_output = output

    def score(self, name, value, data_type="NUMERIC", comment=None) -> None:
        self._tracer.scores.append((name, value))


def test_clip_for_trace_truncates_long_text():
    text = "word " * 2000
    clipped = clip_for_trace(text, max_chars=80)
    assert isinstance(clipped, str)
    assert len(clipped) <= 80
    assert clipped.endswith("…")


def test_clip_for_trace_nested():
    payload = {"code": "print(1)\n" * 500, "items": list(range(20))}
    clipped = clip_for_trace(payload, max_chars=120)
    assert isinstance(clipped, dict)
    assert clipped["code"].endswith("…")
    assert clipped["items"][-1].startswith("…")


def test_noop_tracer_is_safe():
    tracer = get_noop_tracer()
    assert tracer.enabled is False
    with tracer.observation("x", as_type="generation", input={"a": 1}) as obs:
        obs.update(output="ok")
        obs.score("n", 1)
        obs.update_trace(user_id="u1")
    tracer.flush()
    tracer.shutdown()


def test_langfuse_settings_require_keys():
    settings = LangfuseSettings(enabled=True, public_key="", secret_key="x", host="http://x")
    assert settings.is_enabled is False
    settings = LangfuseSettings(
        enabled=True,
        public_key="pk",
        secret_key="sk",
        host="http://langfuse:3000",
    )
    assert settings.is_enabled is True


def test_build_tracer_disabled_without_keys():
    tracer = build_llm_tracer(LangfuseSettings(enabled=False), logger=None)
    assert tracer.enabled is False


def test_trace_async_records_root_and_scores():
    async def _run_test() -> None:
        tracer = RecordingTracer()

        async def _run() -> dict[str, int]:
            return {"score": 8}

        result = await trace_async(
            tracer,
            "review-submission",
            _run,
            as_type="chain",
            input={"submission_id": "1"},
            output_from=lambda item: item,
            scores_from=lambda item: (("review_score", item["score"], {}),),
            flush=True,
        )
        assert result["score"] == 8
        assert tracer.names == ["review-submission"]
        assert tracer.types == ["chain"]
        assert tracer.scores == [("review_score", 8)]
        assert tracer.flushed == 1
        assert tracer.last_output == {"score": 8}

    asyncio.run(_run_test())
