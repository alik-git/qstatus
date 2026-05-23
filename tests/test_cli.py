"""Tests for qstatus CLI behavior."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from qstatus.cli import _should_colorize, main
from qstatus.commands import run_command

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Print package version."""
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "qstatus 0.3.2"


def test_cli_repo_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Emit JSON for a real repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    assert main(["repo", "--cwd", str(repo), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "qstatus_repo_snapshot_v1"
    assert payload["repo"]["root"] == str(repo)
    assert payload["summary"]["worktree_state"] == "clean"
    assert payload["github"]["status"] == "not_requested"


def test_cli_non_repo_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Return clear JSON error for non-repo paths."""
    assert main(["--cwd", str(tmp_path), "--json"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "qstatus_error_v1"
    assert "not a git worktree" in payload["error"]


def test_cli_human_output_has_no_readiness_judgment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Human output should report facts without next-action judgments."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    assert main(["--cwd", str(repo)]) == 0

    output = capsys.readouterr().out
    assert "REPO repo " in output
    assert "STATE clean" in output
    assert "NEXT" not in output
    assert "ready" not in output.lower()


def test_cli_human_output_can_force_color(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Forced color affects human output only."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    assert main(["--cwd", str(repo), "--color", "always"]) == 0

    output = capsys.readouterr().out
    assert "\033[" in output
    assert "\033[2m" not in output
    assert "ahead=\033[" in output


def test_cli_plain_overrides_forced_color(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plain output remains ANSI-free even with forced color."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    assert main(["--cwd", str(repo), "--color", "always", "--plain"]) == 0

    assert "\033[" not in capsys.readouterr().out


def test_cli_json_never_emits_color(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON output stays machine-readable regardless of color options."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    assert main(["--cwd", str(repo), "--json", "--color", "always"]) == 0

    output = capsys.readouterr().out
    assert "\033[" not in output
    assert json.loads(output)["schema_version"] == "qstatus_repo_snapshot_v1"


def test_should_colorize_auto_respects_terminal_and_env() -> None:
    """Auto color follows TTY, NO_COLOR, and TERM=dumb."""
    stream = _FakeTty()

    assert _should_colorize("auto", plain=False, stream=stream, env={}) is True
    assert (
        _should_colorize("auto", plain=False, stream=stream, env={"NO_COLOR": "1"})
        is False
    )
    assert (
        _should_colorize("auto", plain=False, stream=stream, env={"TERM": "dumb"})
        is False
    )
    assert _should_colorize("never", plain=False, stream=stream, env={}) is False
    assert _should_colorize("always", plain=True, stream=stream, env={}) is False


class _FakeTty:
    def isatty(self) -> bool:
        return True


def _git(cwd: Path, *args: str) -> None:
    result = run_command(["git", *args], cwd=cwd, timeout_s=10.0)
    assert result.ok, result.stderr or result.stdout
