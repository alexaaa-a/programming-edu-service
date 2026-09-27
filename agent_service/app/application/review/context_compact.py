import json
import re
from typing import Any


_PRIORITY_MARKERS = (
    "повторная сдача",
    "критерии приёмки",
    "синтаксис",
    "компиляция",
    "тесты",
    "потолок",
    "язык:",
    "[static/",
    "[sandbox/",
    "[tests/",
    "error",
    "ошибка",
    "упали",
)


def compact_text(text: str, max_chars: int = 1200) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    if max_chars <= 1:
        return "…"
    return cleaned[: max_chars - 1].rsplit(" ", 1)[0].strip() + "…"


def compact_tool_facts(text: str, max_chars: int = 3200) -> str:
    raw = (text or "").strip()
    if not raw or len(raw) <= max_chars:
        return raw

    lines = [line.rstrip() for line in raw.splitlines()]
    keep: list[str] = []
    rest: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(marker in lower for marker in _PRIORITY_MARKERS) or stripped.startswith("- ["):
            keep.append(stripped)
        else:
            rest.append(stripped)

    selected: list[str] = []
    size = 0
    for line in keep + rest:
        add = len(line) + 1
        if selected and size + add > max_chars:
            break
        if not selected and add > max_chars:
            selected.append(compact_text(line, max_chars=max_chars))
            break
        selected.append(line)
        size += add
    out = "\n".join(selected).strip()
    if len(out) > max_chars:
        out = compact_text(out, max_chars=max_chars)
    if len(raw) > len(out):
        out = f"{out}\n… [контекст сжат: было {len(raw)} символов]".strip()
    return out


def compact_agent_results(results: Any, *, max_chars: int = 4500) -> dict[str, Any] | str:
    if isinstance(results, str):
        return compact_text(results, max_chars=max_chars)
    if not isinstance(results, dict):
        return compact_text(str(results), max_chars=max_chars)

    out: dict[str, Any] = {}
    for key in ("scorecard", "resumed_from"):
        if key in results:
            out[key] = results[key]

    for key in ("reviewer_review", "bug_review"):
        item = results.get(key)
        out[key] = _compact_review_like(item)

    checks = results.get("acceptance_criteria")
    if isinstance(checks, list):
        out["acceptance_criteria"] = [
            {
                "id": str(item.get("id") or ""),
                "text": compact_text(str(item.get("text") or ""), max_chars=100),
                "passed": bool(item.get("passed")),
                "note": compact_text(str(item.get("note") or ""), max_chars=80),
            }
            for item in checks[:8]
            if isinstance(item, dict)
        ]
        failed = [c for c in out["acceptance_criteria"] if not c["passed"]]
        out["acceptance_summary"] = {
            "total": len(out["acceptance_criteria"]),
            "failed": len(failed),
            "open": [c["text"] for c in failed[:4]],
        }

    challenge = results.get("adversarial_challenge")
    if isinstance(challenge, dict):
        out["adversarial_challenge"] = {
            "agrees": bool(challenge.get("agrees", True)),
            "severity": str(challenge.get("severity") or "low"),
            "score_cap": challenge.get("score_cap"),
            "challenges": [compact_text(str(x), max_chars=120) for x in (challenge.get("challenges") or [])[:4]],
            "missed": [compact_text(str(x), max_chars=120) for x in (challenge.get("missed") or [])[:3]],
            "feedback": compact_text(str(challenge.get("feedback") or ""), max_chars=180),
        }

    report = results.get("tool_report")
    if isinstance(report, dict):
        out["tool_report"] = {
            "language": report.get("language"),
            "syntax_ok": report.get("syntax_ok"),
            "compile_ok": report.get("compile_ok"),
            "tests_run": report.get("tests_run"),
            "tests_passed": report.get("tests_passed"),
            "score_cap": report.get("score_cap"),
            "findings": [
                {
                    "tool": item.get("tool"),
                    "severity": item.get("severity"),
                    "message": compact_text(str(item.get("message") or ""), max_chars=120),
                }
                for item in (report.get("findings") or [])[:6]
                if isinstance(item, dict) and str(item.get("severity") or "") in {"error", "warning", "info"}
            ],
        }
    path = results.get("agent_path")
    if isinstance(path, dict):
        steps = path.get("steps") if isinstance(path.get("steps"), list) else []
        out["agent_path"] = {
            "steps": [
                {
                    "name": str(step.get("name") or ""),
                    "status": str(step.get("status") or ""),
                }
                for step in steps[:16]
                if isinstance(step, dict)
            ]
        }

    encoded = json.dumps(out, ensure_ascii=False)
    if len(encoded) <= max_chars:
        return out
    out.pop("agent_path", None)
    if isinstance(out.get("tool_report"), dict):
        out["tool_report"].pop("findings", None)
    return out


def compact_team_summary(
        reviewer_score: int,
        reviewer_feedback: str,
        bug_score: int,
        bug_feedback: str,
        checks: list[dict[str, Any]] | None = None,
) -> str:
    payload = {
        "reviewer": {
            "score": reviewer_score,
            "feedback": compact_text(reviewer_feedback, max_chars=220),
        },
        "bug": {
            "score": bug_score,
            "feedback": compact_text(bug_feedback, max_chars=220),
        },
        "acceptance": [
            {
                "id": item.get("id"),
                "passed": item.get("passed"),
                "text": compact_text(str(item.get("text") or ""), max_chars=90),
            }
            for item in (checks or [])[:6]
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def compact_huddle_briefing(briefing: str, max_chars: int = 1600) -> str:
    text = (briefing or "").strip()
    if len(text) <= max_chars:
        return text
    blocks = re.split(r"\n\s*\n", text)
    clipped: list[str] = []
    size = 0
    for block in blocks:
        first = block.strip().split("\n", 1)[0]
        first = compact_text(first, max_chars=280)
        if not first:
            continue
        if size + len(first) + 2 > max_chars and clipped:
            break
        clipped.append(first)
        size += len(first) + 2
    out = "\n\n".join(clipped)
    if len(text) > len(out):
        out = f"{out}\n… [заметки коллег сжаты]"
    return out


def _compact_review_like(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    if hasattr(item, "score") and hasattr(item, "feedback"):
        suggestions = list(getattr(item, "suggestions", []) or [])
        return {
            "score": int(getattr(item, "score")),
            "feedback": compact_text(str(getattr(item, "feedback") or ""), max_chars=240),
            "suggestions": [compact_text(str(s), max_chars=100) for s in suggestions[:3]],
        }
    if isinstance(item, dict):
        return {
            "score": item.get("score"),
            "feedback": compact_text(str(item.get("feedback") or ""), max_chars=240),
            "suggestions": [
                compact_text(str(s), max_chars=100) for s in (item.get("suggestions") or [])[:3]
            ],
        }
    return {"feedback": compact_text(str(item), max_chars=240)}
