from dataclasses import dataclass, field

from agent_service.app.application.review.acceptance import CriterionCheck, rubric_score_and_cap
from agent_service.app.application.review.adversarial import (
    ChallengeVerdict,
    adversarial_cap_and_reasons,
)
from agent_service.app.application.review.agent_path import PathVerdict, path_cap_and_reasons
from agent_service.app.application.tools.models import ToolReport


@dataclass(frozen=True, slots=True)
class ScoreCard:
    task: int
    reliability: int
    tools: int
    final: int
    tool_cap: int | None = None
    rubric: int | None = None
    rubric_cap: int | None = None
    adversarial_cap: int | None = None
    process: int | None = None
    process_cap: int | None = None
    reasons: list[str] = field(default_factory=list)

    def as_feedback_line(self) -> str:
        extras = ""
        if self.tool_cap is not None:
            extras += f", потолок инструментов {self.tool_cap}"
        if self.rubric is not None:
            extras += f", критерии {self.rubric}/10"
        if self.rubric_cap is not None:
            extras += f", потолок критериев {self.rubric_cap}"
        if self.adversarial_cap is not None:
            extras += f", потолок независимой проверки {self.adversarial_cap}"
        if self.process is not None:
            extras += f", путь {self.process}/10"
        if self.process_cap is not None:
            extras += f", потолок процесса {self.process_cap}"
        return (
            f"**Итог {self.final}/10.** Задача {self.task}, "
            f"надёжность {self.reliability}, инструменты {self.tools}{extras}."
        )

    def as_prompt_block(self) -> str:
        lines = [
            "Итоговый score уже посчитан по рубрике. Не пересчитывай его и не спорь.",
            f"Задача (качество/соответствие): {self.task}/10",
            f"Надёжность (баги/edge cases): {self.reliability}/10",
            f"Инструменты (измерения): {self.tools}/10",
        ]
        if self.rubric is not None:
            lines.append(f"Критерии приёмки: {self.rubric}/10")
        if self.process is not None:
            lines.append(f"Качество пути агентов: {self.process}/10")
        if self.tool_cap is not None:
            lines.append(f"Жёсткий потолок по фактам: {self.tool_cap}/10")
        if self.rubric_cap is not None:
            lines.append(f"Жёсткий потолок по критериям: {self.rubric_cap}/10")
        if self.adversarial_cap is not None:
            lines.append(f"Жёсткий потолок независимой проверки: {self.adversarial_cap}/10")
        if self.process_cap is not None:
            lines.append(f"Жёсткий потолок по процессу: {self.process_cap}/10")
        lines.append(f"Итог: {self.final}/10")
        if self.reasons:
            lines.append("Почему так:")
            lines.extend(f"- {item}" for item in self.reasons[:8])
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        return {
            "task": self.task,
            "reliability": self.reliability,
            "tools": self.tools,
            "final": self.final,
            "tool_cap": self.tool_cap,
            "rubric": self.rubric,
            "rubric_cap": self.rubric_cap,
            "adversarial_cap": self.adversarial_cap,
            "process": self.process,
            "process_cap": self.process_cap,
            "reasons": list(self.reasons),
        }


def compose_score(
        task: int,
        reliability: int,
        report: ToolReport | None = None,
        checks: list[CriterionCheck] | None = None,
        adversarial: ChallengeVerdict | None = None,
        path: PathVerdict | None = None,
) -> ScoreCard:
    task_score = _clamp(task)
    reliability_score = _clamp(reliability)
    tools_score, tool_cap, tool_reasons = _tools_axis(report)
    rubric_score, rubric_cap, rubric_reasons = rubric_score_and_cap(checks or [])
    adversarial_cap, adversarial_reasons = adversarial_cap_and_reasons(adversarial)
    process_cap, process_reasons = path_cap_and_reasons(path)

    weak = min(task_score, reliability_score)
    strong = max(task_score, reliability_score)
    composed = weak + (strong - weak) // 4
    reasons: list[str] = [
        "слабое звено задаёт базу, сильная ось поднимает не больше четверти разрыва",
    ]

    if task_score <= 3:
        composed = min(composed, task_score + 1)
        reasons.append("задача закрыта слабо — итог не выше оценки задачи + 1")
    if reliability_score <= 3:
        composed = min(composed, reliability_score + 1)
        reasons.append("критичные баги — итог не выше надёжности + 1")
    if tool_cap is not None:
        composed = min(composed, tool_cap)
        reasons.extend(tool_reasons)
    if checks:
        composed = min(composed, rubric_score)
        reasons.extend(rubric_reasons)
        if rubric_cap is not None:
            composed = min(composed, rubric_cap)
    if adversarial_cap is not None:
        composed = min(composed, adversarial_cap)
        reasons.extend(adversarial_reasons)
    elif adversarial_reasons:
        reasons.extend(adversarial_reasons)
    if path is not None:
        composed = min(composed, path.score)
        reasons.extend(process_reasons)
        if process_cap is not None:
            composed = min(composed, process_cap)

    return ScoreCard(
        task=task_score,
        reliability=reliability_score,
        tools=tools_score,
        final=_clamp(composed),
        tool_cap=tool_cap,
        rubric=rubric_score if checks else None,
        rubric_cap=rubric_cap,
        adversarial_cap=adversarial_cap,
        process=path.score if path is not None else None,
        process_cap=process_cap,
        reasons=reasons,
    )


def _tools_axis(report: ToolReport | None) -> tuple[int, int | None, list[str]]:
    if report is None:
        return 10, None, []
    if not report.syntax_ok or not report.compile_ok:
        return 2, 2, ["синтаксис или компиляция сломаны — потолок 2"]
    if report.tests_run and report.tests_passed is False:
        return 4, 4, ["тесты в песочнице упали — потолок 4"]
    error_count = sum(1 for item in report.findings if item.severity == "error")
    if error_count >= 2:
        return 5, 5, ["несколько error от инструментов — потолок 5"]
    warning_count = sum(
        1 for item in report.findings if item.severity == "warning" and item.tool != "memory"
    )
    if warning_count:
        return 7, None, []
    return 10, report.score_cap, []


def _clamp(value: int) -> int:
    return max(1, min(10, int(value)))
