import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from agent_service.app.application.dto import Review
from agent_service.app.application.review.acceptance import (
    AcceptanceCriterion,
    AcceptanceRubric,
    CriterionCheck,
)
from agent_service.app.application.review.adversarial import ChallengeVerdict
from agent_service.app.application.review.agent_path import AgentPath, PathStep
from agent_service.app.application.tools.models import ToolFinding, ToolReport


def review_run_key(submission_id: str, attempt: int | None = None) -> str:
    round_no = attempt if attempt and attempt > 0 else 1
    return f"review:{submission_id}:a{round_no}"


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]


def review_graph_thread_id(
        submission_id: str | None,
        attempt: int | None,
        code: str,
        task_description: str,
        user_id: str | None = None,
) -> str:
    if submission_id:
        sid = str(submission_id)
    else:
        scope = f"{user_id or ''}:{code}:{task_description}"
        sid = f"anon-{content_hash(scope)}"
    return (
        f"{review_run_key(submission_id=sid, attempt=attempt)}"
        f":{content_hash(code)}:{content_hash(task_description)}"
    )


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def dump_review(review: Review) -> dict[str, Any]:
    return {
        "score": review.score,
        "feedback": review.feedback,
        "suggestions": list(review.suggestions),
    }


def load_review(data: dict[str, Any] | None) -> Review | None:
    if not isinstance(data, dict):
        return None
    return Review(
        score=int(data.get("score") or 1),
        feedback=str(data.get("feedback") or ""),
        suggestions=[str(item) for item in (data.get("suggestions") or [])],
    )


def dump_tool_report(report: ToolReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return report.as_dict()


def load_tool_report(data: dict[str, Any] | None) -> ToolReport | None:
    if not isinstance(data, dict):
        return None
    findings = [
        ToolFinding(
            tool=str(item.get("tool") or "unknown"),
            severity=str(item.get("severity") or "info"),
            message=str(item.get("message") or ""),
        )
        for item in (data.get("findings") or [])
        if isinstance(item, dict)
    ]
    return ToolReport(
        language=str(data.get("language") or "unknown"),
        findings=findings,
        syntax_ok=bool(data.get("syntax_ok", True)),
        compile_ok=bool(data.get("compile_ok", True)),
        tests_run=bool(data.get("tests_run", False)),
        tests_passed=data.get("tests_passed"),
        score_cap=_optional_int(data.get("score_cap")),
    )


def dump_rubric(rubric: AcceptanceRubric) -> dict[str, Any]:
    return {
        "criteria": [
            {"id": item.id, "text": item.text, "required": item.required}
            for item in rubric.criteria
        ]
    }


def load_rubric(data: dict[str, Any] | None) -> AcceptanceRubric | None:
    if not isinstance(data, dict):
        return None
    criteria: list[AcceptanceCriterion] = []
    for item in data.get("criteria") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        criteria.append(
            AcceptanceCriterion(
                id=str(item.get("id") or f"c{len(criteria) + 1}"),
                text=text,
                required=bool(item.get("required", True)),
            )
        )
    return AcceptanceRubric(criteria=criteria)


def dump_checks(checks: list[CriterionCheck]) -> list[dict[str, Any]]:
    return [asdict(item) for item in checks]


def load_checks(data: Any) -> list[CriterionCheck]:
    if not isinstance(data, list):
        return []
    out: list[CriterionCheck] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            CriterionCheck(
                id=str(item.get("id") or f"c{len(out) + 1}"),
                text=str(item.get("text") or ""),
                passed=bool(item.get("passed")),
                note=str(item.get("note") or ""),
                required=bool(item.get("required", True)),
                line=item.get("line") if isinstance(item.get("line"), int) else None,
            )
        )
    return out


def dump_challenge(challenge: ChallengeVerdict | None) -> dict[str, Any] | None:
    if challenge is None:
        return None
    return challenge.as_dict()


def load_challenge(data: dict[str, Any] | None) -> ChallengeVerdict | None:
    if not isinstance(data, dict):
        return None
    return ChallengeVerdict(
        agrees=bool(data.get("agrees", True)),
        severity=str(data.get("severity") or "low"),
        score_cap=_optional_int(data.get("score_cap")),
        challenges=[str(item) for item in (data.get("challenges") or [])],
        missed=[str(item) for item in (data.get("missed") or [])],
        feedback=str(data.get("feedback") or ""),
    )


def dump_path(path: AgentPath) -> dict[str, Any]:
    return path.as_dict()


def load_path(data: dict[str, Any] | None) -> AgentPath:
    path = AgentPath()
    if not isinstance(data, dict):
        return path
    for item in data.get("steps") or []:
        if not isinstance(item, dict):
            continue
        path.steps.append(
            PathStep(
                kind=str(item.get("kind") or "step"),
                name=str(item.get("name") or ""),
                status=str(item.get("status") or "ok"),
                detail=str(item.get("detail") or ""),
            )
        )
    return path


def stable_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
