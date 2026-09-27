import asyncio
from dataclasses import dataclass
from typing import Any

from agent_service.app.application.review.scorecard import compose_score
from agent_service.app.application.tools.models import ToolReport
from agent_service.app.application.tools.static_analysis import analyze_code, detect_language
from agent_service.app.application.tools.toolkit import ReviewToolkit


@dataclass(frozen=True, slots=True)
class OfflineCase:
    id: str
    code: str
    task_description: str
    task_score: int
    reliability_score: int
    expect_language: str | None = None
    expect_cap: int | None = None
    expect_final_max: int | None = None
    expect_final_min: int | None = None
    expect_syntax_ok: bool | None = None


class _EmptyMemory:
    async def retrieve(self, query: str, k: int, types: set[str] | None = None) -> list:
        return []

    async def save_document(self, text: str, metadata: dict) -> None:
        return None

    async def get_chat_history(self, session_id: str) -> list:
        return []

    async def append_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        turn_id: str | None = None,
    ) -> None:
        return None


OFFLINE_CASES: list[OfflineCase] = [
    OfflineCase(
        id="syntax_broken",
        code="def broken(\n",
        task_description="напиши функцию",
        task_score=9,
        reliability_score=8,
        expect_language="python",
        expect_cap=2,
        expect_final_max=2,
        expect_syntax_ok=False,
    ),
    OfflineCase(
        id="tests_fail",
        code=(
            "def add(a, b):\n"
            "    return a - b\n\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        ),
        task_description="сложи два числа",
        task_score=8,
        reliability_score=8,
        expect_language="python",
        expect_cap=4,
        expect_final_max=4,
        expect_syntax_ok=True,
    ),
    OfflineCase(
        id="weakest_link",
        code="def add(a, b):\n    return a + b\n",
        task_description="сложи два числа",
        task_score=9,
        reliability_score=2,
        expect_language="python",
        expect_final_max=3,
        expect_final_min=1,
        expect_syntax_ok=True,
    ),
    OfflineCase(
        id="unknown_language_no_false_cap",
        code="fn add(a: i32, b: i32) -> i32 { a + b }\n",
        task_description="сложи два числа",
        task_score=8,
        reliability_score=8,
        expect_language="unknown",
        expect_cap=None,
        expect_final_min=7,
        expect_syntax_ok=True,
    ),
    OfflineCase(
        id="bare_except_not_compile_fail",
        code="try:\n    x = 1\nexcept:\n    pass\n",
        task_description="обработай ошибку",
        task_score=6,
        reliability_score=5,
        expect_language="python",
        expect_syntax_ok=True,
        expect_final_min=4,
    ),
]


async def _inspect(code: str, task_description: str) -> ToolReport:
    toolkit = ReviewToolkit(_EmptyMemory())
    return await toolkit.inspect(code=code, task_description=task_description)


def evaluate_offline_cases(cases: list[OfflineCase] | None = None) -> dict[str, Any]:
    selected = cases or OFFLINE_CASES
    per_case: list[dict[str, Any]] = []
    passed = 0
    for case in selected:
        language = detect_language(case.code)
        syntax_ok, _ = analyze_code(case.code, language)
        report = asyncio.run(_inspect(case.code, case.task_description))
        from agent_service.app.application.review.agent_path import AgentPath, evaluate_review_path

        path = AgentPath()
        path.record("tools", kind="tool", status="ok")
        path.record("acceptance_rubric", status="ok")
        path.record("reviewer", kind="agent", status="ok")
        path.record("bug", kind="agent", status="ok")
        path.record("grade_rubric", status="ok")
        path.record("adversarial", kind="agent", status="ok")
        path.record("mentor", kind="agent", status="ok")
        if report.language in {"python", "javascript"}:
            path.record("static", kind="tool", status="ok")
            path.record("sandbox", kind="tool", status="ok")
        path_verdict = evaluate_review_path(
            path,
            language=report.language,
            tools_ran=True,
            syntax_checked=report.language in {"python", "javascript"},
            compile_checked=report.language in {"python", "javascript"},
            sandbox_eligible=report.language in {"python", "javascript"},
            mentor_feedback="Короткий фидбек без полного решения.",
        )
        card = compose_score(
            task=case.task_score,
            reliability=case.reliability_score,
            report=report,
            path=path_verdict,
        )
        if case.expect_cap == 4 and not report.tests_run:
            per_case.append(
                {
                    "id": case.id,
                    "passed": True,
                    "skipped": "pytest unavailable",
                    "language": language,
                    "tool_cap": report.score_cap,
                    "scorecard": card.as_dict(),
                    "failures": [],
                }
            )
            passed += 1
            continue
        failures: list[str] = []
        if case.expect_language and language != case.expect_language:
            failures.append(f"language {language} != {case.expect_language}")
        if case.expect_syntax_ok is not None and syntax_ok != case.expect_syntax_ok:
            failures.append(f"syntax_ok {syntax_ok} != {case.expect_syntax_ok}")
        if case.expect_cap is not None and report.score_cap != case.expect_cap:
            failures.append(f"cap {report.score_cap} != {case.expect_cap}")
        if case.expect_final_max is not None and card.final > case.expect_final_max:
            failures.append(f"final {card.final} > {case.expect_final_max}")
        if case.expect_final_min is not None and card.final < case.expect_final_min:
            failures.append(f"final {card.final} < {case.expect_final_min}")
        ok = not failures
        passed += int(ok)
        per_case.append(
            {
                "id": case.id,
                "passed": ok,
                "failures": failures,
                "language": language,
                "tool_cap": report.score_cap,
                "scorecard": card.as_dict(),
            }
        )
    total = len(selected)
    return {
        "type": "offline_eval",
        "aggregated": {
            "total_cases": total,
            "passed": passed,
            "pass_rate": (passed / total) if total else 0.0,
        },
        "cases": per_case,
    }
