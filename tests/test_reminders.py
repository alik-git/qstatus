"""Tests for quick_status shell reminder integration."""

from __future__ import annotations

import errno
import os
import pty
import shlex
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from quick_status.cli import main
from quick_status.commands import run_command
from quick_status.reminders import render_reminders_init

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


REMINDER = "Consider using quick-status next time to save time!"


def test_reminders_init_bash_outputs_opt_in_shell(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The reminders command should print Bash integration source only."""
    assert main(["reminders", "init", "bash"]) == 0

    output = capsys.readouterr().out
    assert "__quick_status_reminders_init()" in output
    assert "__quick_status_reminder_maybe_print()" in output
    assert "git()" in output
    assert "[ -t 2 ] || return 0" in output
    assert "QUICK_STATUS_REMINDERS" in output


def test_reminders_init_bash_codex_context_outputs_codex_guards(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The Codex context should print guarded non-interactive Bash source."""
    assert main(["reminders", "init", "bash", "--context", "codex"]) == 0

    output = capsys.readouterr().out
    assert "__quick_status_reminders_init()" in output
    assert '[ -n "${CODEX_THREAD_ID:-}" ] || return 0' in output
    assert '[ "${CODEX_CI:-}" = "1" ] || return 0' in output
    assert '[ -n "${BASH_EXECUTION_STRING:-}" ] || return 0' in output
    assert 'case "codex" in' in output
    assert "__QUICK_STATUS_REMINDERS_CONTEXT__" not in output


def test_reminders_rejects_unsupported_shell(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unsupported shell integrations should fail through argparse."""
    with pytest.raises(SystemExit) as exc_info:
        main(["reminders", "init", "zsh"])

    assert exc_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_reminders_rejects_unsupported_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unsupported reminder contexts should fail through argparse."""
    with pytest.raises(SystemExit) as exc_info:
        main(["reminders", "init", "bash", "--context", "ci"])

    assert exc_info.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_reminders_generated_source_skips_noninteractive_shell(tmp_path: Path) -> None:
    """The generated hook should not define wrappers outside interactive Bash."""
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        f"source {shlex.quote(str(hook))}\ndeclare -F git >/dev/null\n",
    )

    result = _run_bash_script(script, interactive=False)

    assert result.returncode == 1
    assert REMINDER not in result.stderr


def test_reminders_codex_context_initializes_in_bash_c(tmp_path: Path) -> None:
    """Codex mode should initialize in guarded non-interactive bash -c shells."""
    repo = _init_repo(tmp_path)
    hook = _write_hook(tmp_path, context="codex")

    result = _run_bash_command(
        f"source {shlex.quote(str(hook))}; "
        f"cd {shlex.quote(str(repo))}; "
        "git status --short --branch",
        env={
            "CODEX_CI": "1",
            "CODEX_THREAD_ID": "test-thread",
        },
    )

    assert result.returncode == 0
    assert "main" in result.stdout
    assert f"{REMINDER} Try: quick-status repo --plain" in result.stderr


def test_reminders_codex_context_survives_exec_child_bash(tmp_path: Path) -> None:
    """Exported Codex wrappers should survive an exec into the command shell."""
    repo = _init_repo(tmp_path)
    hook = _write_hook(tmp_path, context="codex")

    result = _run_bash_command(
        f"source {shlex.quote(str(hook))}; "
        f"exec bash -c 'cd {shlex.quote(str(repo))}; "
        "declare -F git >/dev/null && git status --short --branch'",
        env={
            "CODEX_CI": "1",
            "CODEX_THREAD_ID": "test-thread",
        },
    )

    assert result.returncode == 0
    assert "main" in result.stdout
    assert f"{REMINDER} Try: quick-status repo --plain" in result.stderr


def test_reminders_codex_context_requires_thread_id(tmp_path: Path) -> None:
    """CODEX_CI alone should not be enough to initialize Codex reminders."""
    hook = _write_hook(tmp_path, context="codex")

    result = _run_bash_command(
        f"source {shlex.quote(str(hook))}; declare -F git >/dev/null",
        env={"CODEX_CI": "1"},
    )

    assert result.returncode == 1
    assert REMINDER not in result.stderr


def test_reminders_codex_context_requires_codex_ci(tmp_path: Path) -> None:
    """CODEX_THREAD_ID alone should not be enough to initialize Codex reminders."""
    hook = _write_hook(tmp_path, context="codex")

    result = _run_bash_command(
        f"source {shlex.quote(str(hook))}; declare -F git >/dev/null",
        env={"CODEX_THREAD_ID": "test-thread"},
    )

    assert result.returncode == 1
    assert REMINDER not in result.stderr


def test_reminders_codex_context_skips_script_file_execution(tmp_path: Path) -> None:
    """Codex mode should not initialize for bash script-file execution."""
    hook = _write_hook(tmp_path, context="codex")
    script = _write_script(
        tmp_path,
        f"source {shlex.quote(str(hook))}\ndeclare -F git >/dev/null\n",
    )

    result = _run_bash_script(
        script,
        interactive=False,
        env={
            "CODEX_CI": "1",
            "CODEX_THREAD_ID": "test-thread",
        },
    )

    assert result.returncode == 1
    assert REMINDER not in result.stderr


def test_reminders_print_after_trigger_and_preserve_stdout(tmp_path: Path) -> None:
    """A repo trigger should preserve command output and print the reminder."""
    repo = _init_repo(tmp_path)
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                f"cd {shlex.quote(str(repo))}",
                "git status --short --branch",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                'exit "$rc"',
            ],
        ),
    )

    rc, output = _run_bash_script_with_pty(script)

    assert rc == 0
    assert "main" in output
    assert "RC:0" in output
    assert f"{REMINDER} Try: quick-status repo --plain" in output


def test_reminders_do_not_print_for_non_trigger_with_tty(tmp_path: Path) -> None:
    """A non-trigger command should keep its normal output and stay quiet."""
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                f"cd {shlex.quote(str(repo))}",
                "git add --dry-run README.md",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                'exit "$rc"',
            ],
        ),
    )

    rc, output = _run_bash_script_with_pty(script)

    assert rc == 0
    assert "README.md" in output
    assert "RC:0" in output
    assert REMINDER not in output


def test_reminders_disable_switch_with_tty(tmp_path: Path) -> None:
    """QUICK_STATUS_REMINDERS=0 should silence otherwise matching commands."""
    repo = _init_repo(tmp_path)
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                f"cd {shlex.quote(str(repo))}",
                "git status --short --branch",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                'exit "$rc"',
            ],
        ),
    )

    rc, output = _run_bash_script_with_pty(
        script,
        env={**_clean_env(), "QUICK_STATUS_REMINDERS": "0"},
    )

    assert rc == 0
    assert "RC:0" in output
    assert REMINDER not in output


def test_reminders_keep_captured_stderr_quiet(tmp_path: Path) -> None:
    """Captured stderr should not receive reminder noise."""
    repo = _init_repo(tmp_path)
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                f"cd {shlex.quote(str(repo))}",
                "git status --short --branch",
            ],
        ),
    )

    result = _run_bash_script(script, interactive=True)

    assert result.returncode == 0
    assert REMINDER not in result.stderr


def test_reminders_preserve_failing_exit_code(tmp_path: Path) -> None:
    """A failing wrapped command should still return its original exit code."""
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                f"cd {shlex.quote(str(tmp_path))}",
                "git rev-parse --show-toplevel",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                'exit "$rc"',
            ],
        ),
    )

    result = _run_bash_script(script, interactive=True)

    assert result.returncode == 128
    assert "RC:128" in result.stdout
    assert REMINDER not in result.stderr


def test_reminders_do_not_print_after_failing_trigger_with_tty(
    tmp_path: Path,
) -> None:
    """A matching command that fails should not add reminder noise."""
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                f"cd {shlex.quote(str(tmp_path))}",
                "git rev-parse --show-toplevel",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                "exit 0",
            ],
        ),
    )

    rc, output = _run_bash_script_with_pty(script)

    assert rc == 0
    assert "RC:128" in output
    assert REMINDER not in output


def test_reminders_env_trigger_matching_is_strict(tmp_path: Path) -> None:
    """Env reminders should trigger only for exact safe status commands."""
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                f"source {shlex.quote(str(hook))}",
                "python3 --version",
                "python3 -c 'print(\"not-trigger\")'",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                'exit "$rc"',
            ],
        ),
    )

    rc, output = _run_bash_script_with_pty(script)

    assert rc == 0
    assert "not-trigger" in output
    assert "RC:0" in output
    assert output.count(REMINDER) == 1
    assert "quick-status env --plain --show-tools" in output


def test_reminders_codex_context_mutating_commands_stay_quiet(tmp_path: Path) -> None:
    """Codex mode should not print reminders for mutating or execution commands."""
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    hook = _write_hook(tmp_path, context="codex")

    result = _run_bash_command(
        f"source {shlex.quote(str(hook))}; "
        f"cd {shlex.quote(str(repo))}; "
        "git add --dry-run README.md; "
        "python3 -c 'print(\"not-trigger\")'",
        env={
            "CODEX_CI": "1",
            "CODEX_THREAD_ID": "test-thread",
        },
    )

    assert result.returncode == 0
    assert "README.md" in result.stdout
    assert "not-trigger" in result.stdout
    assert REMINDER not in result.stderr


def test_reminders_do_not_clobber_existing_shell_function(tmp_path: Path) -> None:
    """Existing shell functions should keep their behavior after loading the hook."""
    hook = _write_hook(tmp_path)
    script = _write_script(
        tmp_path,
        "\n".join(
            [
                'conda() { printf "ORIGINAL_CONDA:%s\\n" "$*"; return 7; }',
                f"source {shlex.quote(str(hook))}",
                "conda info",
                "rc=$?",
                "printf 'RC:%s\\n' \"$rc\"",
                "exit 0",
            ],
        ),
    )

    rc, output = _run_bash_script_with_pty(script)

    assert rc == 0
    assert "ORIGINAL_CONDA:info" in output
    assert "RC:7" in output
    assert REMINDER not in output


def _write_hook(tmp_path: Path, *, context: str = "interactive") -> Path:
    hook = tmp_path / "quick-status-reminders.bash"
    hook.write_text(render_reminders_init("bash", context=context), encoding="utf-8")
    return hook


def _write_script(tmp_path: Path, content: str) -> Path:
    script = tmp_path / f"script-{len(list(tmp_path.glob('script-*.bash')))}.bash"
    script.write_text(content, encoding="utf-8")
    return script


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    return repo


def _git(cwd: Path, *args: str) -> None:
    result = run_command(["git", *args], cwd=cwd, timeout_s=10.0)
    assert result.ok, result.stderr or result.stdout


def _run_bash_script(
    script: Path,
    *,
    interactive: bool,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [_bash_path(), "--noprofile", "--norc"]
    if interactive:
        args.append("-i")
    args.append(str(script))
    return subprocess.run(  # noqa: S603
        args,
        env=_clean_env(env),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_bash_command(
    command: str,
    *,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [_bash_path(), "--noprofile", "--norc", "-c", command],
        env=_clean_env(env),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_bash_script_with_pty(
    script: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    master_fd, slave_fd = pty.openpty()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(  # noqa: S603
            [_bash_path(), "--noprofile", "--norc", "-i", str(script)],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=_clean_env(env),
            close_fds=True,
        )
        os.close(slave_fd)
        slave_fd = -1
        output = _read_pty_until_exit(master_fd, process)
        return process.wait(timeout=1.0), output
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        if slave_fd >= 0:
            os.close(slave_fd)
        os.close(master_fd)


def _read_pty_until_exit(master_fd: int, process: subprocess.Popen[bytes]) -> str:
    chunks: list[bytes] = []
    deadline = time.monotonic() + 10.0
    while True:
        try:
            chunk = os.read(master_fd, 4096)
        except OSError as exc:
            if exc.errno == errno.EIO:
                break
            raise
        if chunk:
            chunks.append(chunk)
        if process.poll() is not None:
            break
        if time.monotonic() > deadline:
            process.kill()
            raise AssertionError("timed out waiting for interactive bash smoke test")
    return b"".join(chunks).decode("utf-8", errors="replace")


def _bash_path() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required for reminder integration tests")
    return bash


def _clean_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("BASH_ENV", None)
    env.pop("CODEX_CI", None)
    env.pop("CODEX_THREAD_ID", None)
    if overrides:
        env.update(overrides)
    return env
