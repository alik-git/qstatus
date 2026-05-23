"""Safe subprocess helpers for qstatus."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from qstatus.models import CommandRecord

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
        )


def run_command(
    args: Sequence[str],
    *,
    cwd: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> CommandResult:
    """Run a command without a shell and return captured output."""
    command = tuple(str(arg) for arg in args)
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
            unavailable=True,
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
        )
    return CommandResult(
        args=command,
        cwd=cwd,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
