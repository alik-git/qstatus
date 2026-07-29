"""Safe subprocess helpers for quick_status."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from quick_status.models import CommandRecord

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


DEFAULT_TIMEOUT_S = 3.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Completed external command result."""

    args: tuple[str, ...]
    cwd: Path
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    unavailable: bool = False
    duration_ms: float = 0.0
    source: str = "live"
    collected_at: str | None = None
    age_seconds: float | None = None

    @property
    def ok(self) -> bool:
        """Return true when the command completed successfully."""
        return self.exit_code == 0 and not self.timed_out and not self.unavailable

    def evidence(self) -> CommandRecord:
        """Return a compact command evidence record."""
        return CommandRecord(
            args=list(self.args),
            cwd=str(self.cwd),
            exit_code=self.exit_code,
            timed_out=self.timed_out,
            unavailable=self.unavailable,
            stderr=self.stderr.strip(),
            duration_ms=round(self.duration_ms, 3),
            source=self.source,
            collected_at=self.collected_at,
            age_seconds=self.age_seconds,
        )


def run_command(
    args: Sequence[str],
    *,
    cwd: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> CommandResult:
    """Run a command without a shell and return captured output."""
    command = tuple(str(arg) for arg in args)
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            args=command,
            cwd=cwd,
            exit_code=None,
            stdout="",
            stderr=str(exc),
            unavailable=exc.filename == command[0],
            duration_ms=(time.perf_counter() - started) * 1000,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(
            args=command,
            cwd=cwd,
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
    return CommandResult(
        args=command,
        cwd=cwd,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=(time.perf_counter() - started) * 1000,
    )
