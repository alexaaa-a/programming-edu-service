import re
from dataclasses import dataclass


IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
QUOTED = re.compile(r"`([^`]{2,80})`|«([^»]{2,80})»|\"([^\"]{2,80})\"|'([^']{2,80})'")
EXPLICIT = re.compile(
    r"(?:строк[аеуи]{1,2}|стр\.?|line|строке)\s*№?\s*(\d{1,4})|:(\d{1,4}):",
    re.IGNORECASE,
)

STOP_WORDS = frozenset(
    {
        "none",
        "true",
        "false",
        "null",
        "self",
        "return",
        "import",
        "class",
        "def",
        "function",
        "const",
        "error",
        "value",
        "type",
        "test",
        "code",
    }
)

DECLARATION = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"|^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(?:function|\(|async)",
)


@dataclass(frozen=True, slots=True)
class Anchor:
    line: int
    source: str


def anchor_line(text: str, code: str, hint: int | None = None) -> int | None:
    found = anchor(text, code, hint)
    return found.line if found is not None else None


def anchor(text: str, code: str, hint: int | None = None) -> Anchor | None:
    lines = (code or "").splitlines()
    if not lines:
        return None
    total = len(lines)

    if hint is not None and 1 <= int(hint) <= total:
        return Anchor(line=int(hint), source="model")

    explicit = _explicit_line(text or "")
    if explicit is not None and 1 <= explicit <= total:
        return Anchor(line=explicit, source="text")

    for snippet in _quoted(text or ""):
        line = _find_snippet(snippet, lines)
        if line is not None:
            return Anchor(line=line, source="snippet")

    for name in _identifiers(text or ""):
        line = _find_symbol(name, lines)
        if line is not None:
            return Anchor(line=line, source="symbol")
    return None


def _explicit_line(text: str) -> int | None:
    match = EXPLICIT.search(text)
    if match is None:
        return None
    raw = match.group(1) or match.group(2)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _quoted(text: str) -> list[str]:
    found: list[str] = []
    for match in QUOTED.finditer(text):
        snippet = next((group for group in match.groups() if group), "").strip()
        if snippet and len(snippet) >= 2 and not _looks_like_prose(snippet):
            found.append(snippet)
    return found[:4]


def _identifiers(text: str) -> list[str]:
    seen: list[str] = []
    for match in IDENT.finditer(text):
        name = match.group(0)
        if name.lower() in STOP_WORDS or name.lower() in {item.lower() for item in seen}:
            continue
        seen.append(name)
    return seen[:6]


def _find_snippet(snippet: str, lines: list[str]) -> int | None:
    for index, line in enumerate(lines, start=1):
        if snippet in line:
            return index
    lowered = snippet.lower()
    for index, line in enumerate(lines, start=1):
        if lowered in line.lower():
            return index
    return None


def _find_symbol(name: str, lines: list[str]) -> int | None:
    word = re.compile(rf"\b{re.escape(name)}\b")
    first_use: int | None = None
    for index, line in enumerate(lines, start=1):
        if not word.search(line):
            continue
        declaration = DECLARATION.match(line)
        if declaration is not None and name in {declaration.group(1), declaration.group(2)}:
            return index
        if first_use is None:
            first_use = index
    return first_use


def _looks_like_prose(snippet: str) -> bool:
    if re.search(r"[а-яё]", snippet, re.IGNORECASE):
        return True
    return len(snippet.split()) > 4
