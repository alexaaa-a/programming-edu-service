from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Union


MAX_CHOICE_OPTIONS = 255
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


@dataclass(frozen=True, slots=True)
class Noul:
    name: str
    instructions: str
    if_true: str
    if_false: str

    kind: str = "noul"

    def payload(self) -> dict[str, Any]:
        return {
            "type": "noul",
            "instructions": self.instructions,
            "criteria": {"true": self.if_true, "false": self.if_false},
        }


@dataclass(frozen=True, slots=True)
class Choice:
    name: str
    instructions: str
    options: Mapping[str, str]

    kind: str = "choice"

    def __post_init__(self) -> None:
        if not 2 <= len(self.options) <= MAX_CHOICE_OPTIONS:
            raise ValueError(
                f"choice '{self.name}': нужно от 2 до {MAX_CHOICE_OPTIONS} вариантов, "
                f"получено {len(self.options)}"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "type": "choice",
            "instructions": self.instructions,
            "criteria": {str(key): str(value) for key, value in self.options.items()},
        }


@dataclass(frozen=True, slots=True)
class Score:
    name: str
    instructions: str
    levels: Sequence[str]

    kind: str = "score"

    def __post_init__(self) -> None:
        if not MIN_SCORE_LEVELS <= len(self.levels) <= MAX_SCORE_LEVELS:
            raise ValueError(
                f"score '{self.name}': нужно от {MIN_SCORE_LEVELS} до {MAX_SCORE_LEVELS} "
                f"уровней, получено {len(self.levels)}"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": self.instructions,
            "criteria": [str(level) for level in self.levels],
        }


Question = Union[Noul, Choice, Score]


@dataclass(frozen=True, slots=True)
class ChoiceAnswer:
    value: str
    confidence: float
    probabilities: Mapping[str, float] = field(default_factory=dict)

    @property
    def p_top(self) -> float:
        if not self.probabilities:
            return 0.0
        return float(max(self.probabilities.values()))

    @property
    def margin(self) -> float:
        if len(self.probabilities) < 2:
            return self.p_top
        ordered = sorted(self.probabilities.values(), reverse=True)
        return float(ordered[0] - ordered[1])


@dataclass(frozen=True, slots=True)
class ScoreAnswer:
    value: float
    confidence: float
    levels: int
    probabilities: Mapping[int, float] = field(default_factory=dict)

    @property
    def level(self) -> int:
        return int(round(self.value))

    @property
    def normalized(self) -> float:
        span = max(self.levels - 1, 1)
        return min(max(self.value / span, 0.0), 1.0)


@dataclass(frozen=True, slots=True)
class Answers:
    items: Mapping[str, Any] = field(default_factory=dict)
    source: str = "jev"
    reason: str = ""
    latency_ms: float = 0.0
    model: str = ""

    @classmethod
    def unavailable(cls, reason: str, latency_ms: float = 0.0) -> "Answers":
        return cls(items={}, source="unavailable", reason=reason, latency_ms=latency_ms)

    def __bool__(self) -> bool:
        return bool(self.items)

    def noul(self, name: str) -> float | None:
        value = self.items.get(name)
        if isinstance(value, float):
            return value
        return None

    def choice(self, name: str, min_confidence: float = 0.0) -> ChoiceAnswer | None:
        value = self.items.get(name)
        if not isinstance(value, ChoiceAnswer):
            return None
        if value.confidence < min_confidence:
            return None
        return value

    def score(self, name: str, min_confidence: float = 0.0) -> ScoreAnswer | None:
        value = self.items.get(name)
        if not isinstance(value, ScoreAnswer):
            return None
        if value.confidence < min_confidence:
            return None
        return value

    def holds(self, name: str, threshold: float) -> bool:
        probability = self.noul(name)
        return probability is not None and probability >= threshold


def questions_payload(questions: Sequence[Question]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for question in questions:
        if question.name in payload:
            raise ValueError(f"дубль имени вопроса: {question.name}")
        payload[question.name] = question.payload()
    return payload


def parse_answers(
        body: Mapping[str, Any],
        questions: Sequence[Question],
        latency_ms: float = 0.0,
) -> Answers:
    raw = body.get("answers")
    if not isinstance(raw, Mapping):
        return Answers.unavailable("no_answers", latency_ms=latency_ms)

    expected = {question.name: question for question in questions}
    items: dict[str, Any] = {}
    for name, answer in raw.items():
        question = expected.get(str(name))
        if question is None or not isinstance(answer, Mapping):
            continue
        parsed = _parse_one(question, answer)
        if parsed is not None:
            items[str(name)] = parsed
    if not items:
        return Answers.unavailable("no_known_answers", latency_ms=latency_ms)
    return Answers(
        items=items,
        source="jev",
        reason="ok",
        latency_ms=latency_ms,
        model=str(body.get("model") or ""),
    )


def _parse_one(question: Question, answer: Mapping[str, Any]) -> Any:
    if question.kind == "noul":
        probability = _as_float(answer.get("noul"))
        if probability is None:
            probability = _as_float(answer.get("probability"))
        if probability is None:
            return None
        return min(max(probability, 0.0), 1.0)

    if question.kind == "choice":
        value = str(answer.get("choice") or "").strip()
        if value not in question.options:
            return None
        probabilities = {
            str(key): float(prob)
            for key, prob in _as_mapping(answer.get("probabilities")).items()
            if _as_float(prob) is not None
        }
        confidence = _as_float(answer.get("confidence"))
        if confidence is None:
            confidence = probabilities.get(value, 0.0)
        return ChoiceAnswer(
            value=value,
            confidence=min(max(confidence, 0.0), 1.0),
            probabilities=probabilities,
        )

    value = _as_float(answer.get("score"))
    if value is None:
        return None
    probabilities: dict[int, float] = {}
    for key, prob in _as_mapping(answer.get("probabilities")).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        as_float = _as_float(prob)
        if as_float is not None:
            probabilities[index] = as_float
    confidence = _as_float(answer.get("confidence"))
    return ScoreAnswer(
        value=value,
        confidence=min(max(confidence if confidence is not None else 0.0, 0.0), 1.0),
        levels=len(question.levels),
        probabilities=probabilities,
    )


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
