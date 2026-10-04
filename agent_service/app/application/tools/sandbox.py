import asyncio
import os
import resource
import shutil
import sys
import tempfile
from pathlib import Path

from agent_service.app.application.tools.models import ToolFinding


_TIMEOUT_COMPILE = 8.0
_TIMEOUT_TESTS = 5.0
_ENV = (
    os.environ.get("APP_ENV")
    or os.environ.get("ENVIRONMENT")
    or os.environ.get("ENV")
    or "dev"
).strip().lower()
_ALLOW_LIVE_TESTS = (
    os.environ.get("AGENT_SERVICE_SANDBOX_RUN_TESTS", "").strip().lower()
    in {"1", "true", "yes"}
    and _ENV not in {"prod", "production"}
)
_MEM_BYTES = int(os.environ.get("AGENT_SERVICE_SANDBOX_MEM_MB", "256")) * 1024 * 1024
_CPU_SEC = int(os.environ.get("AGENT_SERVICE_SANDBOX_CPU_SEC", "5"))


def looks_like_tests(code: str) -> bool:
    return "def test_" in code or "class Test" in code


async def compile_python(code: str) -> ToolFinding | None:
    finding, _ = await _run_in_temp(
        filename="solution.py",
        code=code,
        argv=[sys.executable, "-m", "py_compile", "solution.py"],
        timeout=_TIMEOUT_COMPILE,
        tool="sandbox",
        fail_prefix="Код не компилируется",
    )
    return finding


async def compile_javascript(code: str) -> ToolFinding | None:
    node = shutil.which("node")
    if node is None:
        return ToolFinding(
            "sandbox",
            "error",
            "JS проверка недоступна: node не найден в окружении",
        )
    finding, _ = await _run_in_temp(
        filename="solution.js",
        code=code,
        argv=[node, "--check", "solution.js"],
        timeout=_TIMEOUT_COMPILE,
        tool="sandbox",
        fail_prefix="JS не проходит node --check",
    )
    return finding


async def run_python_tests(code: str) -> tuple[bool | None, ToolFinding | None]:
    if not looks_like_tests(code):
        return None, None
    if not _ALLOW_LIVE_TESTS:
        return None, ToolFinding(
            "tests",
            "info",
            "Песочница: live pytest отключён (AGENT_SERVICE_SANDBOX_RUN_TESTS)",
        )
    argv = _test_argv()
    if argv is None:
        return None, None
    finding, returncode = await _run_in_temp(
        filename="test_solution.py",
        code=code,
        argv=argv,
        timeout=_TIMEOUT_TESTS,
        tool="tests",
        fail_prefix="Тесты в песочнице упали",
    )
    if returncode == 0:
        return True, None
    if returncode == 5:
        return None, None
    if finding is None:
        return None, None
    if "timeout" in finding.message.lower() or "лимит" in finding.message:
        return None, finding
    return False, finding


def _test_argv() -> list[str] | None:
    try:
        import pytest
    except ImportError:
        return None
    return [
        sys.executable,
        "-m",
        "pytest",
        "test_solution.py",
        "-q",
        "--tb=line",
        "-p",
        "no:cacheprovider",
    ]


def _sandbox_preexec() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_SEC, _CPU_SEC))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_MEM_BYTES, _MEM_BYTES))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    except (ValueError, OSError):
        pass


async def _run_in_temp(
        filename: str,
        code: str,
        argv: list[str],
        timeout: float,
        tool: str,
        fail_prefix: str,
) -> tuple[ToolFinding | None, int | None]:
    finding, returncode, _ = await run_files(
        files={filename: code},
        argv=argv,
        timeout=timeout,
        tool=tool,
        fail_prefix=fail_prefix,
    )
    return finding, returncode


async def run_files(
        files: dict[str, str],
        argv: list[str],
        timeout: float,
        tool: str,
        fail_prefix: str,
        collect: str | None = None,
) -> tuple[ToolFinding | None, int | None, str | None]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
        "NO_PROXY": "*",
        "OPENAI_API_KEY": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "AWS_ACCESS_KEY_ID": "",
    }
    with tempfile.TemporaryDirectory(prefix="desk-sandbox-") as tmp:
        for name, text in files.items():
            (Path(tmp) / name).write_text(text, encoding="utf-8")
        try:
            kwargs: dict = {
                "cwd": tmp,
                "env": env,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if os.name == "posix":
                kwargs["preexec_fn"] = _sandbox_preexec
            proc = await asyncio.create_subprocess_exec(*argv, **kwargs)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolFinding(tool, "error", f"{fail_prefix}: лимит {timeout:.0f}с"), None, None
        except FileNotFoundError as exc:
            missing = argv[0] if argv else "binary"
            return (
                ToolFinding(
                    tool,
                    "error",
                    f"{fail_prefix}: среда недоступна ({missing} не найден: {exc})",
                ),
                None,
                None,
            )
        collected: str | None = None
        if collect is not None:
            report = Path(tmp) / collect
            if report.exists():
                collected = report.read_text(encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            return None, 0, collected
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        detail = _trim(detail, 400)
        return (
            ToolFinding(tool, "error", f"{fail_prefix}: {detail or 'ненулевой код выхода'}"),
            proc.returncode,
            collected,
        )


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
