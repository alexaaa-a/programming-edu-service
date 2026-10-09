import re
from dataclasses import dataclass, field
from typing import Mapping
from uuid import UUID, uuid5


NAMESPACE = UUID("8f1c2e4a-4d9b-5f7a-9c3e-1b6d8a2f4c70")

GROUP_PREFIX = "student_"

STUDENT = "Student"
SKILL = "Skill"
ERROR_PATTERN = "ErrorPattern"
TASK = "Task"
PREFERENCE = "Preference"

NODE_LABELS: frozenset[str] = frozenset({STUDENT, SKILL, ERROR_PATTERN, TASK, PREFERENCE})

STRUGGLES_WITH = "STRUGGLES_WITH"
DEMONSTRATES = "DEMONSTRATES"
EXHIBITS = "EXHIBITS"
PREFERS = "PREFERS"
WORKED_ON = "WORKED_ON"
PRACTISES = "PRACTISES"
INSTANCE_OF = "INSTANCE_OF"


@dataclass(frozen=True, slots=True)
class RelationSpec:
    name: str
    source_label: str
    target_label: str
    summary: str
    contradicts: str = ""
    single_valid: bool = True


RELATIONS: tuple[RelationSpec, ...] = (
    RelationSpec(
        name=STRUGGLES_WITH,
        source_label=STUDENT,
        target_label=SKILL,
        summary="the student keeps failing criteria that belong to this skill",
        contradicts=DEMONSTRATES,
    ),
    RelationSpec(
        name=DEMONSTRATES,
        source_label=STUDENT,
        target_label=SKILL,
        summary="the student handled this skill correctly, confirmed by evidence",
        contradicts=STRUGGLES_WITH,
    ),
    RelationSpec(
        name=EXHIBITS,
        source_label=STUDENT,
        target_label=ERROR_PATTERN,
        summary="the student repeats this concrete mistake in submitted code",
    ),
    RelationSpec(
        name=PREFERS,
        source_label=STUDENT,
        target_label=PREFERENCE,
        summary="how the student prefers to be taught or helped",
    ),
    RelationSpec(
        name=WORKED_ON,
        source_label=STUDENT,
        target_label=TASK,
        summary="the student submitted code for this task",
        single_valid=False,
    ),
    RelationSpec(
        name=PRACTISES,
        source_label=TASK,
        target_label=SKILL,
        summary="the task exercises this skill",
    ),
    RelationSpec(
        name=INSTANCE_OF,
        source_label=ERROR_PATTERN,
        target_label=SKILL,
        summary="the mistake belongs to this skill",
    ),
)

RELATION_BY_NAME: dict[str, RelationSpec] = {spec.name: spec for spec in RELATIONS}

EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {}
for _spec in RELATIONS:
    EDGE_TYPE_MAP.setdefault((_spec.source_label, _spec.target_label), []).append(_spec.name)


def relation_allowed(name: str, source_label: str, target_label: str) -> bool:
    spec = RELATION_BY_NAME.get(name)
    if spec is None:
        return False
    return spec.source_label == source_label and spec.target_label == target_label


@dataclass(frozen=True, slots=True)
class SkillNode:
    id: str
    name: str
    summary: str
    patterns: tuple[str, ...] = field(default_factory=tuple)


SKILLS: tuple[SkillNode, ...] = (
    SkillNode(
        id="requirements",
        name="Requirements and task logic",
        summary="The code does exactly what the brief asks: input, output, result shape.",
        patterns=("requirement", "brief", "spec", "business logic", "требован", "бриф", "по заданию", "услови"),
    ),
    SkillNode(
        id="edge_cases",
        name="Edge cases",
        summary="Empty input, boundaries, duplicates, overflow and other corner cases.",
        patterns=("edge case", "corner case", "boundary", "empty input", "гранич", "крайн", "пуст"),
    ),
    SkillNode(
        id="validation",
        name="Input validation and types",
        summary="Untrusted input is checked before use; types match the contract.",
        patterns=("validation", "validate", "type check", "schema", "валид", "типиз", "провер* вход"),
    ),
    SkillNode(
        id="error_handling",
        name="Error handling",
        summary="Failures are raised, caught and reported instead of being swallowed.",
        patterns=("error handling", "exception", "try/except", "bare except", "swallow", "ошибк", "исключен", "except"),
    ),
    SkillNode(
        id="testing",
        name="Testing",
        summary="Tests exist, are meaningful and fail when the behaviour breaks.",
        patterns=("test", "assert", "coverage", "тест", "покрыти"),
    ),
    SkillNode(
        id="algorithms",
        name="Algorithms and complexity",
        summary="The chosen algorithm fits the data size; complexity is reasonable.",
        patterns=("algorithm", "complexity", "o(n", "performance", "алгоритм", "сложност"),
    ),
    SkillNode(
        id="data_structures",
        name="Data structures",
        summary="The data layout matches the access pattern.",
        patterns=("data structure", "dict", "list", "set", "структур данн", "словар", "список"),
    ),
    SkillNode(
        id="code_quality",
        name="Code readability and structure",
        summary="Naming, decomposition and the absence of duplication.",
        patterns=("readability", "naming", "duplication", "refactor", "читаем", "именован", "дублиров"),
    ),
    SkillNode(
        id="api_design",
        name="API design and contracts",
        summary="Interfaces, status codes and response shape stay predictable.",
        patterns=("api", "endpoint", "contract", "status code", "контракт", "эндпоинт"),
    ),
    SkillNode(
        id="data_storage",
        name="Database access",
        summary="Queries, indexes, transactions and the shape of stored data.",
        patterns=("database", "query", "index", "transaction", "sql", "база данн", "запрос", "индекс"),
    ),
    SkillNode(
        id="async_concurrency",
        name="Asynchrony and concurrency",
        summary="Blocking calls, races and task lifetimes in concurrent code.",
        patterns=("async", "await", "concurrency", "race", "асинхрон", "конкурент", "блокиру"),
    ),
    SkillNode(
        id="security",
        name="Security",
        summary="Secrets, injections and access checks.",
        patterns=("security", "injection", "secret", "auth", "безопасн", "инъекц", "секрет", "доступ"),
    ),
    SkillNode(
        id="frontend_ui",
        name="UI and state",
        summary="Component state, rendering and user-visible behaviour.",
        patterns=("ui", "component", "render", "state", "интерфейс", "компонент", "состояни"),
    ),
    SkillNode(
        id="observability",
        name="Logging and metrics",
        summary="What the running code reports about itself.",
        patterns=("logging", "logger", "metric", "trace", "лог", "метрик", "трасс"),
    ),
)

SKILL_BY_ID: dict[str, SkillNode] = {skill.id: skill for skill in SKILLS}
SKILL_IDS: frozenset[str] = frozenset(SKILL_BY_ID)

FALLBACK_SKILL = "requirements"

SKILL_ALIASES: Mapping[str, str] = {
    "requirement": "requirements",
    "spec": "requirements",
    "business_logic": "requirements",
    "edge_case": "edge_cases",
    "boundaries": "edge_cases",
    "input_validation": "validation",
    "types": "validation",
    "exceptions": "error_handling",
    "error": "error_handling",
    "errors": "error_handling",
    "tests": "testing",
    "unit_testing": "testing",
    "algorithm": "algorithms",
    "complexity": "algorithms",
    "data_structure": "data_structures",
    "readability": "code_quality",
    "style": "code_quality",
    "refactoring": "code_quality",
    "api": "api_design",
    "contracts": "api_design",
    "database": "data_storage",
    "db": "data_storage",
    "storage": "data_storage",
    "sql": "data_storage",
    "async": "async_concurrency",
    "concurrency": "async_concurrency",
    "asyncio": "async_concurrency",
    "auth": "security",
    "authorization": "security",
    "frontend": "frontend_ui",
    "ui": "frontend_ui",
    "logging": "observability",
    "metrics": "observability",
    "monitoring": "observability",
}


def normalize_skill_id(raw: str | None) -> str | None:
    key = _slug(raw)
    if not key:
        return None
    if key in SKILL_IDS:
        return key
    alias = SKILL_ALIASES.get(key)
    if alias:
        return alias
    singular = key[:-1] if key.endswith("s") else f"{key}s"
    if singular in SKILL_IDS:
        return singular
    return SKILL_ALIASES.get(singular)


def classify_skill(text: str) -> str | None:
    blob = (text or "").lower()
    if not blob.strip():
        return None
    best: tuple[int, str] | None = None
    for skill in SKILLS:
        hits = sum(1 for pattern in skill.patterns if _pattern_hit(pattern, blob))
        if hits and (best is None or hits > best[0]):
            best = (hits, skill.id)
    return best[1] if best else None


def _pattern_hit(pattern: str, blob: str) -> bool:
    if "*" in pattern:
        return re.search(pattern.replace("*", r"\w*"), blob) is not None
    return pattern in blob


ERROR_PATTERNS: Mapping[str, tuple[str, str]] = {
    "bare_except": ("error_handling", "Catches every exception with a bare except and hides the failure"),
    "swallowed_error": ("error_handling", "Catches an exception and returns silently without reporting it"),
    "missing_error_path": ("error_handling", "Happy path only: the failure branch is never written"),
    "no_input_validation": ("validation", "Uses input without checking its type or range"),
    "wrong_types": ("validation", "Passes or returns values of the wrong type"),
    "empty_input_unhandled": ("edge_cases", "Breaks on empty input or an empty collection"),
    "off_by_one": ("edge_cases", "Off-by-one error at a boundary"),
    "mutable_default": ("code_quality", "Mutable value as a default argument"),
    "duplicated_logic": ("code_quality", "The same logic is copied instead of extracted"),
    "unclear_naming": ("code_quality", "Names do not say what the value is"),
    "god_function": ("code_quality", "One function does several unrelated things"),
    "missing_tests": ("testing", "Submits behaviour that no test covers"),
    "tautological_test": ("testing", "The test passes even when the behaviour is broken"),
    "quadratic_scan": ("algorithms", "Nested scan where a single pass or a lookup would do"),
    "wrong_collection": ("data_structures", "Uses a list where a set or a dict is required"),
    "ignores_brief": ("requirements", "Solves a different problem than the brief asks for"),
    "wrong_result_shape": ("requirements", "Returns a different shape than the brief requires"),
    "blocking_call_in_async": ("async_concurrency", "Blocking call inside asynchronous code"),
    "unawaited_coroutine": ("async_concurrency", "Coroutine is created but never awaited"),
    "n_plus_one_query": ("data_storage", "Queries the database inside a loop"),
    "secret_in_code": ("security", "Keeps a secret or a token in the source"),
    "unsafe_eval": ("security", "Executes input with eval or exec"),
    "no_logging": ("observability", "Failure leaves no trace in the logs"),
}


def normalize_pattern_slug(raw: str | None) -> str | None:
    text = str(raw or "")
    if any(ch.isalpha() and not ch.isascii() for ch in text):
        return None
    slug = _slug(text)
    if not slug or len(slug) < 3:
        return None
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,47}", slug):
        return None
    return slug


def skill_of_pattern(slug: str) -> str | None:
    known = ERROR_PATTERNS.get(slug)
    return known[0] if known else None


def pattern_summary(slug: str) -> str:
    known = ERROR_PATTERNS.get(slug)
    if known:
        return known[1]
    return slug.replace("_", " ").capitalize()


def group_id_for(user_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(user_id or "").strip())
    if not safe:
        raise ValueError("group_id requires a user_id")
    return f"{GROUP_PREFIX}{safe}"


def user_id_of_group(group_id: str) -> str:
    text = str(group_id or "")
    return text[len(GROUP_PREFIX):] if text.startswith(GROUP_PREFIX) else text


def node_uuid(group_id: str, label: str, key: str) -> str:
    return str(uuid5(NAMESPACE, f"{group_id}|{label}|{key}"))


def _slug(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    text = text.replace("-", "_").replace(" ", "_").replace("/", "_")
    text = re.sub(r"[^a-z0-9_]", "", text)
    return re.sub(r"_+", "_", text).strip("_")
