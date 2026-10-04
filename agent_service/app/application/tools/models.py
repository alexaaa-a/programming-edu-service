from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolFinding:
    tool: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolReport:
    language: str
    findings: list[ToolFinding] = field(default_factory=list)
    syntax_ok: bool = True
    compile_ok: bool = True
    tests_run: bool = False
    tests_passed: bool | None = None
    score_cap: int | None = None
    hidden: Any | None = None

    def as_prompt_block(self) -> str:
        supported = self.language in {"python", "javascript"}
        if supported:
            lines = [f"Язык: {self.language}"]
            lines.append(f"Синтаксис: {'ok' if self.syntax_ok else 'ошибка'}")
            lines.append(f"Компиляция: {'ok' if self.compile_ok else 'ошибка'}")
            if self.tests_run:
                if self.tests_passed is True:
                    lines.append("Тесты в песочнице: прошли")
                elif self.tests_passed is False:
                    lines.append("Тесты в песочнице: упали")
                else:
                    lines.append("Тесты в песочнице: запускались, результат неясен")
            else:
                skipped = any(
                    ("отключ" in f.message.lower() or "sandbox_run_tests" in f.message.lower())
                    for f in self.findings
                )
                if skipped:
                    lines.append(
                        "Тесты в песочнице: не запускались (live pytest отключён политикой)"
                    )
                else:
                    lines.append("Тесты в песочнице: не запускались (в коде нет test_)")
        else:
            lines = [
                f"Язык: {self.language}",
                "Инструменты static/sandbox/tests этот язык не проверяют.",
                "Не выдумывай ошибки компиляции и не режь score из-за отсутствия проверки.",
                "Оценивай по коду, задаче и базе знаний.",
            ]
        if self.hidden is not None:
            lines.extend(_hidden_lines(self.hidden))
        if self.score_cap is not None:
            lines.append(f"Потолок скора по фактам инструментов: {self.score_cap}/10")
        if self.findings:
            lines.append("Находки:")
            for item in self.findings[:12]:
                lines.append(f"- [{item.tool}/{item.severity}] {item.message}")
        else:
            lines.append("Находки: нет")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "syntax_ok": self.syntax_ok,
            "compile_ok": self.compile_ok,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "score_cap": self.score_cap,
            "hidden_tests": _hidden_dict(self.hidden),
            "findings": [
                {"tool": f.tool, "severity": f.severity, "message": f.message}
                for f in self.findings
            ],
        }


def _hidden_lines(run: Any) -> list[str]:
    status = getattr(run, "status", "")
    if status == "passed":
        return [
            f"Тесты задачи: пройдены все {getattr(run, 'total', 0)}.",
            "Это факт, а не мнение: код запускался. Не пиши, что решение не работает.",
        ]
    if status == "failed":
        names = ", ".join(getattr(run, "failed_names", [])[:5]) or "без имён"
        return [
            f"Тесты задачи: прошло {getattr(run, 'passed', 0)} из {getattr(run, 'total', 0)}.",
            f"Упали: {names}.",
            "Это факт: код запускался. Критерии, которые закрывают упавшие тесты, не могут быть выполнены.",
        ]
    if status == "error":
        return [
            f"Тесты задачи не прогнались: {getattr(run, 'detail', '') or 'ошибка запуска'}.",
            "Считай это отказом решения, а не отсутствием проверки.",
        ]
    if status == "timeout":
        return [
            "Тесты задачи не уложились в лимит времени: решение зациклилось или слишком медленное.",
        ]
    return ["Тесты задачи: у задачи их нет, оценивай по критериям."]


def _hidden_dict(run: Any) -> dict[str, object] | None:
    if run is None:
        return None
    return {
        "status": getattr(run, "status", ""),
        "total": getattr(run, "total", 0),
        "passed": getattr(run, "passed", 0),
        "failed": getattr(run, "failed", 0),
        "failed_names": list(getattr(run, "failed_names", []))[:10],
        "detail": getattr(run, "detail", ""),
    }
