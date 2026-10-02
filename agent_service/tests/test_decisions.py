import asyncio
import json
from types import SimpleNamespace

import pytest

from agent_service.app.application.decisions import (
    Choice,
    Noul,
    Score,
    chat_turn_questions,
    chat_turn_state,
    memory_keep_question,
    parse_answers,
    peer_review_question,
    questions_payload,
    read_chat_turn,
    rerank_questions,
    rerank_state,
)
from agent_service.app.application.decisions.questions import Answers
from agent_service.app.config import JevSettings
from agent_service.app.infrastructure.decisions import DisabledDecisionModel, JevDecisionModel


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload or {}, ensure_ascii=False)

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _Client:
    def __init__(self, *responses) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def post(self, url: str, json: dict, headers: dict, timeout: float):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        item = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def _settings(**kwargs) -> JevSettings:
    base = {
        "enabled": True,
        "api_key": "test-key",
        "model": "typesafe/jev-1.13",
        "min_confidence": 0.6,
        "failure_threshold": 2,
        "cooldown_sec": 30.0,
    }
    base.update(kwargs)
    return JevSettings(**base)


def _model(client: _Client, clock=None, **kwargs) -> JevDecisionModel:
    return JevDecisionModel(
        client=client,
        settings=_settings(**kwargs),
        clock=clock or (lambda: 0.0),
    )


def test_question_payload_matches_decisions_api():
    payload = questions_payload(
        [
            Noul("is_bug", "Это баг?", if_true="описано сломанное поведение", if_false="это вопрос"),
            Choice("team", "Чья зона?", {"qa": "тесты и падения", "arch": "границы модулей"}),
            Score("severity", "Насколько критично?", ["косметика", "мешает", "блокер"]),
        ]
    )
    assert payload["is_bug"] == {
        "type": "noul",
        "instructions": "Это баг?",
        "criteria": {"true": "описано сломанное поведение", "false": "это вопрос"},
    }
    assert payload["team"]["type"] == "choice"
    assert set(payload["team"]["criteria"]) == {"qa", "arch"}
    # у score критерии — упорядоченный список уровней, а не словарь
    assert payload["severity"]["criteria"] == ["косметика", "мешает", "блокер"]


def test_choice_needs_at_least_two_options_and_score_at_most_ten_levels():
    with pytest.raises(ValueError):
        Choice("one", "?", {"only": "единственный вариант"})
    with pytest.raises(ValueError):
        Score("long", "?", [str(index) for index in range(11)])
    with pytest.raises(ValueError):
        questions_payload([Noul("dup", "?", "a", "b"), Noul("dup", "?", "c", "d")])


def test_parse_answers_reads_three_primitives():
    questions = [
        Noul("escalate", "?", "да", "нет"),
        Choice("route", "?", {"billing": "оплата", "bug": "поломка"}),
        Score("urgency", "?", ["низко", "средне", "высоко"]),
    ]
    body = {
        "model": "jev-1.13.0",
        "answers": {
            "escalate": {"type": "noul", "noul": 0.96},
            "route": {
                "type": "choice",
                "choice": "billing",
                "confidence": 0.99,
                "probabilities": {"billing": 0.99, "bug": 0.01},
            },
            "urgency": {
                "type": "score",
                "score": 1.87,
                "legend": {"0": "низко", "1": "средне", "2": "высоко"},
                "probabilities": {"0": 0.01, "1": 0.11, "2": 0.88},
                "confidence": 0.86,
            },
        },
    }
    answers = parse_answers(body, questions, latency_ms=120.0)

    assert answers.noul("escalate") == pytest.approx(0.96)
    assert answers.holds("escalate", 0.9) is True
    assert answers.holds("escalate", 0.99) is False

    route = answers.choice("route", min_confidence=0.9)
    assert route is not None and route.value == "billing"
    assert route.margin == pytest.approx(0.98)
    assert answers.choice("route", min_confidence=0.995) is None

    urgency = answers.score("urgency")
    assert urgency is not None
    assert urgency.level == 2
    assert urgency.normalized == pytest.approx(0.935)
    assert answers.model == "jev-1.13.0" and answers.latency_ms == 120.0


def test_parse_answers_drops_unknown_and_impossible_values():
    questions = [Choice("route", "?", {"a": "первый", "b": "второй"})]
    body = {
        "answers": {
            "route": {"type": "choice", "choice": "c", "confidence": 1.0},
            "whatever": {"type": "noul", "noul": 1.0},
        }
    }
    # вариант, которого нет в перечислении, отбрасывается целиком
    assert not parse_answers(body, questions)
    assert parse_answers({}, questions).reason == "no_answers"


def test_disabled_model_answers_nothing():
    answers = asyncio.run(DisabledDecisionModel().ask("state", [Noul("x", "?", "a", "b")]))
    assert not answers and answers.reason == "disabled"
    assert DisabledDecisionModel().enabled is False


def test_client_posts_decisions_request_and_parses_answers():
    client = _Client(
        _Response(200, {"answers": {"keep": {"type": "noul", "noul": 0.8}}, "usage": {"input_tokens": 90}})
    )
    model = _model(client)
    answers = asyncio.run(
        model.ask({"text": "разбор"}, [memory_keep_question("chat_episode")], label="memory_write_gate")
    )

    call = client.calls[0]
    assert call["url"].endswith("/alpha/decisions")
    assert call["json"]["model"] == "typesafe/jev-1.13"
    assert call["json"]["state"] == {"text": "разбор"}
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert answers.noul("keep") == pytest.approx(0.8)


def test_client_survives_http_error_timeout_and_garbage():
    for response in (
        _Response(429, None, text="rate limited"),
        _Response(200, None, text="not json"),
        TimeoutError("slow"),
    ):
        client = _Client(response)
        answers = asyncio.run(_model(client).ask("state", [Noul("x", "?", "a", "b")]))
        assert not answers
        assert answers.noul("x") is None


def test_client_pauses_after_repeated_failures_and_resumes_after_cooldown():
    now = {"t": 0.0}
    client = _Client(_Response(500, None, text="boom"))
    model = _model(client, clock=lambda: now["t"])

    for _ in range(2):
        asyncio.run(model.ask("state", [Noul("x", "?", "a", "b")]))
    assert len(client.calls) == 2

    # порог неудач достигнут: запросы не уходят, пока не пройдёт пауза
    answers = asyncio.run(model.ask("state", [Noul("x", "?", "a", "b")]))
    assert len(client.calls) == 2 and answers.reason == "cooldown"

    now["t"] = 31.0
    asyncio.run(model.ask("state", [Noul("x", "?", "a", "b")]))
    assert len(client.calls) == 3


def test_no_key_means_no_request():
    client = _Client(_Response(200, {"answers": {}}))
    model = JevDecisionModel(client=client, settings=_settings(api_key=" "))
    answers = asyncio.run(model.ask("state", [Noul("x", "?", "a", "b")]))
    assert model.enabled is False and not client.calls and answers.reason == "disabled"


def test_chat_turn_policy_reads_route_and_scaffolding():
    questions = chat_turn_questions()
    body = {
        "answers": {
            "speaker": {
                "type": "choice",
                "choice": "emma",
                "confidence": 0.91,
                "probabilities": {"emma": 0.91, "john": 0.05, "sara": 0.02, "mike": 0.02},
            },
            "huddle": {"type": "noul", "noul": 0.2},
            "solution_seeking": {"type": "noul", "noul": 0.88},
            "frustration": {"type": "score", "score": 2.6, "confidence": 0.8},
        }
    }
    policy = read_chat_turn(parse_answers(body, questions), min_confidence=0.6)

    assert policy is not None
    assert policy.speaker_id == "emma" and policy.huddle is False
    assert policy.solution_seeking is True and policy.frustration == 3
    lines = policy.coach_lines()
    assert any("готовый код" in line or "Готовый код" in line for line in lines)
    assert any("Один шаг" in line for line in lines)


def test_chat_turn_policy_ignores_unconfident_speaker():
    questions = chat_turn_questions()
    body = {
        "answers": {
            "speaker": {
                "type": "choice",
                "choice": "john",
                "confidence": 0.3,
                "probabilities": {"john": 0.3, "emma": 0.28, "sara": 0.22, "mike": 0.2},
            },
            "huddle": {"type": "noul", "noul": 0.1},
            "solution_seeking": {"type": "noul", "noul": 0.1},
            "frustration": {"type": "score", "score": 0.2, "confidence": 0.9},
        }
    }
    assert read_chat_turn(parse_answers(body, questions), min_confidence=0.6) is None
    assert read_chat_turn(Answers.unavailable("disabled"), min_confidence=0.6) is None


def test_chat_turn_state_is_data_not_prompt():
    state = chat_turn_state(
        message="почему падает на пустом списке",
        task_title="Пагинация заказов",
        task_description="описание",
        briefing="шаг: правка",
        history_tail=["user: привет", "assistant: привет"],
    )
    assert state["message"].startswith("почему")
    assert state["task_title"] == "Пагинация заказов"
    assert state["recent_messages"] == ["user: привет", "assistant: привет"]


def test_rerank_questions_match_documents():
    questions = rerank_questions(3)
    assert [question.name for question in questions] == ["doc_0", "doc_1", "doc_2"]
    state = rerank_state("вопрос", ["а", "б", "в"])
    assert set(state["documents"]) == {"#0", "#1", "#2"}


def test_peer_review_question_keeps_player_text_as_data():
    question = peer_review_question("нет проверки пустого списка")
    payload = question.payload()
    assert payload["type"] == "noul"
    assert "нет проверки пустого списка" in payload["criteria"]["true"]
    # просьбы внутри заметки заранее объявлены данными
    assert "текст игрока" in payload["criteria"]["false"]


def test_tracer_observation_is_opened_for_each_request():
    events: list[str] = []

    class _Obs:
        def update(self, **kwargs) -> None:
            events.append("update")

    class _Tracer:
        def observation(self, name, **kwargs):
            events.append(name)

            class _Ctx:
                def __enter__(self_inner):
                    return _Obs()

                def __exit__(self_inner, *args):
                    return False

            return _Ctx()

    client = _Client(_Response(200, {"answers": {"keep": {"type": "noul", "noul": 0.9}}}))
    model = JevDecisionModel(
        client=client,
        settings=_settings(),
        tracer=_Tracer(),
        metrics=SimpleNamespace(
            increment=lambda *a, **k: None,
            record_duration_seconds=lambda *a, **k: None,
        ),
    )
    asyncio.run(model.ask("state", [memory_keep_question("chat_episode")]))
    assert events[0] == "decisions.ask" and "update" in events
