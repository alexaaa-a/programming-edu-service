import json
import re
from typing import Any, Iterable, Mapping, Sequence

from agent_service.app.application.graph_memory.facts import (
    EpisodeKind,
    FactOperation,
    FactTarget,
    GraphFact,
    MemoryEpisode,
    SourceKind,
    StoredFact,
)
from agent_service.app.application.graph_memory.ontology import (
    DEMONSTRATES,
    EXHIBITS,
    PREFERS,
    RELATION_BY_NAME,
    SKILL_BY_ID,
    STRUGGLES_WITH,
    WORKED_ON,
    classify_skill,
    normalize_pattern_slug,
    normalize_skill_id,
    pattern_summary,
    relation_allowed,
    skill_of_pattern,
)


MAX_STATEMENT_CHARS = 220
MAX_MODEL_FACTS = 6
MAX_DETERMINISTIC_FACTS = 10

MODEL_RELATIONS: frozenset[str] = frozenset({EXHIBITS, PREFERS, STRUGGLES_WITH, DEMONSTRATES})


def observations_to_facts(episode: MemoryEpisode) -> list[GraphFact]:
    facts: list[GraphFact] = []
    criteria = [item for item in episode.observations if item.get("kind") == "criterion"]
    tests = next((item for item in episode.observations if item.get("kind") == "hidden_tests"), None)
    tests_status = str((tests or {}).get("status") or "")
    tests_red = tests_status in {"failed", "error", "timeout"}

    if episode.task_id:
        facts.append(
            _fact(
                episode,
                relation=WORKED_ON,
                target=FactTarget("task", str(episode.task_id), episode.task_title),
                statement=_worked_on_statement(episode),
                source=SourceKind.REVIEW,
                confidence=1.0,
            )
        )

    failed_skills: set[str] = set()
    passed_skills: set[str] = set()
    for item in criteria:
        text = f"{item.get('text') or ''} {item.get('note') or ''}"
        skill_id = classify_skill(text)
        if skill_id is None:
            continue
        if item.get("passed"):
            passed_skills.add(skill_id)
        else:
            failed_skills.add(skill_id)

    passed_skills -= failed_skills

    for skill_id in sorted(failed_skills):
        facts.append(
            _fact(
                episode,
                relation=STRUGGLES_WITH,
                target=_skill_target(skill_id),
                statement=(
                    f"The student failed acceptance criteria for "
                    f"{SKILL_BY_ID[skill_id].name.lower()} in this submission."
                ),
                source=SourceKind.REVIEW,
                confidence=0.75,
            )
        )

    if not tests_red:
        source = SourceKind.HIDDEN_TESTS if tests_status == "passed" else SourceKind.REVIEW
        confidence = 0.8 if tests_status == "passed" else 0.55
        for skill_id in sorted(passed_skills):
            facts.append(
                _fact(
                    episode,
                    relation=DEMONSTRATES,
                    target=_skill_target(skill_id),
                    statement=(
                        f"The student met the acceptance criteria for "
                        f"{SKILL_BY_ID[skill_id].name.lower()}"
                        + (" and the hidden tests passed." if tests_status == "passed" else ".")
                    ),
                    source=source,
                    confidence=confidence,
                )
            )

    if tests is not None and tests_status == "failed":
        facts.extend(_failed_test_facts(episode, tests, fallback=sorted(failed_skills)))

    return _dedupe(facts)[:MAX_DETERMINISTIC_FACTS]


def _failed_test_facts(
        episode: MemoryEpisode,
        tests: Mapping[str, Any],
        fallback: list[str],
) -> list[GraphFact]:
    names = [str(name) for name in (tests.get("failed_names") or []) if str(name).strip()]
    skills: list[str] = []
    for name in names[:8]:
        skill_id = classify_skill(name.replace("_", " "))
        if skill_id and skill_id not in skills:
            skills.append(skill_id)
    if not skills:
        skills = fallback[:2]
    total = int(tests.get("total") or 0)
    passed = int(tests.get("passed") or 0)
    detail = f"{max(0, total - passed)} of {total} hidden tests failed" if total else "hidden tests failed"
    return [
        _fact(
            episode,
            relation=STRUGGLES_WITH,
            target=_skill_target(skill_id),
            statement=(
                f"Execution disagrees with the submission: {detail} on "
                f"{SKILL_BY_ID[skill_id].name.lower()}."
            ),
            source=SourceKind.HIDDEN_TESTS,
            confidence=0.9,
        )
        for skill_id in skills
    ]


def fixed_pattern_facts(
        episode: MemoryEpisode,
        exhibited: Sequence[StoredFact],
) -> list[GraphFact]:
    tests = next((item for item in episode.observations if item.get("kind") == "hidden_tests"), None)
    if tests is None or str(tests.get("status") or "") != "passed" or int(tests.get("total") or 0) <= 0:
        return []

    failed_skills: set[str] = set()
    for item in episode.observations:
        if item.get("kind") != "criterion" or item.get("passed"):
            continue
        skill_id = classify_skill(f"{item.get('text') or ''} {item.get('note') or ''}")
        if skill_id:
            failed_skills.add(skill_id)

    out: list[GraphFact] = []
    for stored in exhibited:
        if stored.relation != EXHIBITS or not stored.is_valid:
            continue
        skill_id = pattern_skill(stored.target)
        if skill_id is None or skill_id in failed_skills:
            continue
        out.append(
            _fact(
                episode,
                relation=EXHIBITS,
                target=stored.target,
                statement=(
                    f"The student no longer shows '{stored.target.key}': the hidden tests "
                    "passed and no criterion for that skill failed."
                ),
                source=SourceKind.HIDDEN_TESTS,
                confidence=0.85,
                operation=FactOperation.INVALIDATE,
            )
        )
    return out


EXTRACTION_SYSTEM = (
    "You maintain the long-term memory of a programming student. "
    "You turn one episode into a few durable facts. "
    "A durable fact is something still useful in two weeks: a recurring mistake, "
    "a confirmed skill gap, a confirmed strength, or how the student prefers to be helped. "
    "Never record one-off details, task wording, scores, or anything you only suspect. "
    "Answer in English only, even when the episode is in another language."
)


def extraction_prompt(episode: MemoryEpisode, known_patterns: Iterable[str] = ()) -> str:
    skills = "\n".join(f"- {skill.id}: {skill.summary}" for skill in SKILL_BY_ID.values())
    catalogue = ", ".join(sorted(set(known_patterns))) or "(none yet)"
    observations = _observations_block(episode)
    relations = (
        f"- {STRUGGLES_WITH}: target_kind=skill, the student repeatedly fails this skill\n"
        f"- {DEMONSTRATES}: target_kind=skill, the student handled this skill correctly\n"
        f"- {EXHIBITS}: target_kind=error_pattern, a concrete recurring mistake in the code\n"
        f"- {PREFERS}: target_kind=preference, how the student wants to be taught or helped"
    )
    return (
        f"Episode kind: {episode.kind.value}\n"
        f"Task: {episode.task_title or 'unknown'}\n"
        f"{observations}\n\n"
        f"Episode body:\n{_clip(episode.body, 3200)}\n\n"
        f"Allowed relations:\n{relations}\n\n"
        f"Allowed skill ids (use these exactly):\n{skills}\n\n"
        f"Error patterns already in this student's memory: {catalogue}\n"
        "Reuse an existing error pattern slug when the mistake is the same one.\n\n"
        "Return a JSON array, at most "
        f"{MAX_MODEL_FACTS} items, no prose around it. Each item:\n"
        '{"relation": "...", "target_kind": "skill|error_pattern|preference", '
        '"target_key": "snake_case_id", "statement": "one English sentence about the student", '
        '"status": "present|resolved", "confidence": 0.0-1.0}\n'
        'Use "status": "resolved" only when the episode shows the student no longer does this — '
        "then the stored fact is closed instead of a new one being added.\n"
        "Rules: target_key for skill must be one of the ids above; for error_pattern and "
        "preference it is a short snake_case slug. The statement must describe the student, "
        "not the task. Return [] when the episode holds nothing durable."
    )


def parse_extraction(raw: str, episode: MemoryEpisode) -> list[GraphFact]:
    items = _load_json_array(raw)
    facts: list[GraphFact] = []
    for item in items[: MAX_MODEL_FACTS * 2]:
        fact = _fact_from_item(item, episode)
        if fact is not None:
            facts.append(fact)
    return _dedupe(facts)[:MAX_MODEL_FACTS]


def _fact_from_item(item: Any, episode: MemoryEpisode) -> GraphFact | None:
    if not isinstance(item, Mapping):
        return None
    relation = str(item.get("relation") or "").strip().upper()
    if relation not in MODEL_RELATIONS or relation not in RELATION_BY_NAME:
        return None
    kind = str(item.get("target_kind") or "").strip().lower()
    target = _normalize_target(kind, item.get("target_key"))
    if target is None:
        return None
    if not relation_allowed(relation, RELATION_BY_NAME[relation].source_label, target.label):
        return None
    statement = _clean_statement(item.get("statement"), target)
    if not statement:
        return None
    confidence = _clamp(item.get("confidence"), default=0.6)
    source = SourceKind.CHAT if episode.kind is EpisodeKind.CHAT else SourceKind.REVIEW
    resolved = str(item.get("status") or "present").strip().lower() == "resolved"
    return _fact(
        episode,
        relation=relation,
        target=target,
        statement=statement,
        source=source,
        confidence=confidence,
        operation=FactOperation.INVALIDATE if resolved else FactOperation.ADD,
    )


def _normalize_target(kind: str, raw_key: Any) -> FactTarget | None:
    if kind == "skill":
        skill_id = normalize_skill_id(str(raw_key or ""))
        return _skill_target(skill_id) if skill_id else None
    if kind == "error_pattern":
        slug = normalize_pattern_slug(str(raw_key or ""))
        return FactTarget("error_pattern", slug, pattern_summary(slug)) if slug else None
    if kind == "preference":
        slug = normalize_pattern_slug(str(raw_key or ""))
        return FactTarget("preference", slug, slug.replace("_", " ")) if slug else None
    return None


def pattern_skill(target: FactTarget) -> str | None:
    if target.kind != "error_pattern":
        return None
    known = skill_of_pattern(target.key)
    if known:
        return known
    return classify_skill(f"{target.key.replace('_', ' ')} {target.name}")


def _fact(
        episode: MemoryEpisode,
        relation: str,
        target: FactTarget,
        statement: str,
        source: SourceKind,
        confidence: float,
        operation: FactOperation = FactOperation.ADD,
) -> GraphFact:
    return GraphFact(
        user_id=episode.user_id,
        relation=relation,
        target=target,
        statement=_clip(statement, MAX_STATEMENT_CHARS),
        source=source,
        operation=operation,
        confidence=max(0.0, min(1.0, float(confidence))),
        occurred_at=episode.occurred_at,
        task_id=episode.task_id,
        submission_id=episode.submission_id,
        session_id=episode.session_id,
        writer="memory_curator" if episode.kind is EpisodeKind.REVIEW else "chat_curator",
    )


def _skill_target(skill_id: str) -> FactTarget:
    skill = SKILL_BY_ID[skill_id]
    return FactTarget("skill", skill.id, skill.name)


def _worked_on_statement(episode: MemoryEpisode) -> str:
    title = (episode.task_title or "").strip()
    return f"The student submitted code for task {episode.task_id}" + (f" ({title})." if title else ".")


def _observations_block(episode: MemoryEpisode) -> str:
    if not episode.observations:
        return "Observations: none"
    lines: list[str] = ["Observations:"]
    for item in episode.observations[:16]:
        kind = str(item.get("kind") or "")
        if kind == "criterion":
            mark = "passed" if item.get("passed") else "FAILED"
            lines.append(f"- criterion [{mark}]: {_clip(str(item.get('text') or ''), 160)}")
        elif kind == "hidden_tests":
            lines.append(
                f"- hidden tests: {item.get('status')} "
                f"({item.get('passed')}/{item.get('total')})"
            )
        elif kind == "challenge":
            lines.append(f"- objection: {_clip(str(item.get('text') or ''), 160)}")
        elif kind == "score":
            lines.append(f"- score: {item.get('value')}/10")
    return "\n".join(lines)


def _clean_statement(raw: Any, target: FactTarget) -> str:
    text = " ".join(str(raw or "").split())
    if len(text) < 12:
        return ""
    if not re.search(r"[A-Za-z]", text):
        return ""
    return _clip(text, MAX_STATEMENT_CHARS)


def _load_json_array(raw: str) -> list[Any]:
    text = (raw or "").strip()
    if not text:
        return []
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start: end + 1])
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _dedupe(facts: list[GraphFact]) -> list[GraphFact]:
    seen: set[str] = set()
    out: list[GraphFact] = []
    for fact in facts:
        if fact.key in seen:
            continue
        seen.add(fact.key)
        out.append(fact)
    return out


def _clamp(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _clip(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"
