import ast
import re

from agent_service.app.application.tools.models import ToolFinding


_PYTHON = "python"
_JAVASCRIPT = "javascript"
_UNKNOWN = "unknown"

_PYTHON_MARKERS = (
    (r"\bdef\s+\w+\s*\([^)]*\)\s*:", 2),
    (r"\bdef\s+\w+\s*\(", 2),
    (r"\basync\s+def\b", 2),
    (r"\btry\s*:", 2),
    (r"\belif\b", 2),
    (r"\bexcept\b", 2),
    (r"\bNone\b", 1),
    (r"\bself\.", 1),
    (r"\bif\s+__name__\s*==", 2),
    (r"^\s*from\s+[\w.]+\s+import\b", 2),
    (r"^\s*import\s+[\w.]+", 1),
)
_JS_MARKERS = (
    (r"\bfunction\s+\w+\s*\(", 2),
    (r"\bconst\s+\w+\s*=", 1),
    (r"\blet\s+\w+\s*=", 1),
    (r"=>", 2),
    (r"\bexport\s+(default|const|function|class|interface)\b", 2),
    (r"\binterface\s+\w+", 1),
    (r"console\.log", 1),
    (r"===", 1),
)


def detect_language(code: str) -> str:
    head = code.lstrip()
    first = head.splitlines()[0] if head else ""
    if re.match(r"^#!.*\bpython(\d+(\.\d+)*)?\b", first):
        return _PYTHON
    if re.match(r"^#!.*\b(node|nodejs)\b", first):
        return _JAVASCRIPT

    sample = head[:2000]
    python_score = _score(sample, _PYTHON_MARKERS)
    js_score = _score(sample, _JS_MARKERS)

    if re.search(r"^\s*def\s+\w+", sample, re.M) and re.search(r"^\s*end\b", sample, re.M):
        python_score -= 2
    if "func " in sample or "package " in sample or "fn " in sample:
        python_score -= 1
        js_score -= 1

    if python_score >= 2 and python_score > js_score:
        return _PYTHON
    if js_score >= 2 and js_score > python_score:
        return _JAVASCRIPT
    return _UNKNOWN


def analyze_python(code: str) -> tuple[bool, list[ToolFinding]]:
    findings: list[ToolFinding] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        where = f"строка {e.lineno}" if e.lineno else "неизвестная строка"
        msg = e.msg or "синтаксическая ошибка"
        return False, [ToolFinding("static", "error", f"Синтаксис: {msg} ({where})")]

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(
                ToolFinding("static", "warning", f"Голый except (строка {node.lineno}) — глушит все ошибки"),
            )
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                findings.append(
                    ToolFinding("static", "warning", f"except + pass (строка {node.lineno}) — ошибка проглатывается"),
                )
        if isinstance(node, ast.FunctionDef):
            if _is_empty_body(node.body) and not node.name.startswith("_"):
                findings.append(
                    ToolFinding("static", "warning", f"Пустая функция `{node.name}` (строка {node.lineno})"),
                )
            for arg in node.args.defaults:
                if isinstance(arg, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        ToolFinding(
                            "static",
                            "warning",
                            f"Мутабельный дефолт в `{node.name}` (строка {node.lineno})",
                        ),
                    )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            findings.append(
                ToolFinding("static", "error", f"Вызов {node.func.id}() (строка {node.lineno}) — так нельзя в сдаче"),
            )

    if re.search(r"\bTODO\b|\bFIXME\b", code):
        findings.append(ToolFinding("static", "info", "В коде остались TODO/FIXME"))

    return True, findings[:10]


def analyze_javascript(code: str) -> tuple[bool, list[ToolFinding]]:
    findings: list[ToolFinding] = []
    if code.count("{") != code.count("}"):
        findings.append(ToolFinding("static", "error", "Несбалансированные фигурные скобки"))
        return False, findings
    if code.count("(") != code.count(")"):
        findings.append(ToolFinding("static", "error", "Несбалансированные круглые скобки"))
        return False, findings
    if re.search(r"\beval\s*\(", code):
        findings.append(ToolFinding("static", "error", "Вызов eval() — так нельзя в сдаче"))
    if re.search(r"function\s+\w+\s*\([^)]*\)\s*\{\s*\}", code):
        findings.append(ToolFinding("static", "warning", "Есть пустая function"))
    return True, findings[:10]


def analyze_code(code: str, language: str) -> tuple[bool, list[ToolFinding]]:
    if language == _JAVASCRIPT:
        return analyze_javascript(code)
    if language == _PYTHON:
        return analyze_python(code)
    return True, [
        ToolFinding(
            "static",
            "info",
            "Язык не python/javascript — синтаксис и песочница пропущены, оценивай по коду и задаче",
        ),
    ]


def _score(sample: str, markers: tuple[tuple[str, int], ...]) -> int:
    return sum(weight for pattern, weight in markers if re.search(pattern, sample, re.M))


def _is_empty_body(body: list[ast.stmt]) -> bool:
    if not body:
        return True
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return True
    if len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        return body[0].value.value is Ellipsis or body[0].value.value is None
    return False
