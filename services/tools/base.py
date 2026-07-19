"""Shared subprocess helpers for pinned tools."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


class ToolExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        tool: str,
        exit_code: int | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.tool = tool
        self.exit_code = exit_code
        self.stderr = stderr


@dataclass
class SubprocessResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    runtime_seconds: float
    timed_out: bool = False


@dataclass
class ToolAvailability:
    ready: bool
    tool: str
    executable: str | None = None
    version: str | None = None
    database_path: str | None = None
    database_version: str | None = None
    errors: list[str] = field(default_factory=list)


def which(candidates: list[str]) -> str | None:
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int,
    env: dict[str, str] | None = None,
) -> SubprocessResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return SubprocessResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            runtime_seconds=time.perf_counter() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return SubprocessResult(
            command=command,
            exit_code=None,  # type: ignore[arg-type]
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "timeout",
            runtime_seconds=time.perf_counter() - started,
            timed_out=True,
        )


def normalize_fraction(value: float | None) -> float | None:
    """Normalize identity/coverage that may be 0-1 or 0-100 into 0-1."""
    if value is None:
        return None
    if value > 1.0:
        return max(0.0, min(1.0, value / 100.0))
    return max(0.0, min(1.0, value))


def slugify(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in text.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "unknown"
