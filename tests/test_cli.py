"""Tests for quick_status CLI behavior."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

import quick_status.cli
import quick_status.git_snapshot
from quick_status import __version__
from quick_status.cli import _should_colorize, main
from quick_status.commands import CommandResult, run_command
from quick_status.models import GitHubContext, RemoteCheckSummary

if TYPE_CHECKING:
    from pathlib import Path


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    """Print package version."""
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"quick-status {__version__}"


def test_cli_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """Top-level help should show the repo/env/ci command surface."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "Commands:" in output
    assert "quick-status [repo]" in output
    assert "quick-status env" in output
    assert "quick-status ci" in output
    assert "quick-status reminders" in output
    assert "quick-status repo --worktrees" in output


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
    assert payload["schema_version"] == "quick_status_repo_snapshot_v1"
    assert payload["repo"]["root"] == str(repo)
    assert payload["summary"]["worktree_state"] == "clean"
    assert payload["github"]["status"] == "not_requested"
    assert payload["worktree"]["worktrees"][0]["is_current"] is True
    assert payload["stashes"]["detail_status"] == "not_requested"


def test_cli_repo_json_can_include_stash_entries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Repo JSON includes bounded stash detail only when requested."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    (repo / "README.md").write_text("# Test\n\nWIP\n")
    _git(repo, "stash", "push", "-m", "wip before moving worktree")

    assert main(["repo", "--cwd", str(repo), "--json", "--stashes"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["changes"]["stash_count"] == 1
    assert payload["stashes"]["detail_status"] == "available"
    assert payload["stashes"]["entries"][0]["ref"] == "stash@{0}"
    assert payload["stashes"]["entries"][0]["file_count"] == 1
    assert "wip before moving worktree" in payload["stashes"]["entries"][0]["subject"]


def test_cli_non_repo_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Return clear JSON error for non-repo paths."""
    assert main(["--cwd", str(tmp_path), "--json"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "quick_status_error_v1"
    assert "not a git worktree" in payload["error"]


def test_cli_missing_git_reports_missing_tool(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not misreport a missing git executable as a non-repo path."""

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        del timeout_s
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=None,
            stdout="",
            stderr="missing git",
            unavailable=True,
        )

    monkeypatch.setattr(quick_status.git_snapshot, "run_command", fake_run_command)

    assert main(["repo", "--cwd", str(tmp_path), "--json"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "quick_status_error_v1"
    assert payload["error"] == "git is not installed or not on PATH"


def test_cli_env_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Emit ANSI-free JSON for quick_status env."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "example"\nrequires-python = ">=3.11"\n',
    )

    assert main(["env", "--cwd", str(tmp_path), "--json", "--color", "always"]) == 0

    output = capsys.readouterr().out
    assert "\033[" not in output
    payload = json.loads(output)
    assert payload["schema_version"] == "quick_status_env_snapshot_v1"
    assert payload["project"]["name"] == "example"


def test_cli_env_human_uses_structured_sections(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Human env output should mirror JSON sections instead of long packed rows."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "example"\n')

    assert main(["env", "--cwd", str(tmp_path), "--plain"]) == 0

    output = capsys.readouterr().out
    assert "SHELL\n" in output
    assert "  cwd  " in output
    assert "PYTHON\n" in output
    assert "  runtime  " in output
    assert "  python" in output
    assert "python3=" in output
    assert "PROJECT\n" in output
    assert "name=example" in output
    assert "TOOLS\n" not in output
    assert "HINTS" not in output
    assert "ENV shell=" not in output


def test_cli_env_human_can_show_optional_sections(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Optional env sections stay hidden unless requested."""
    (tmp_path / "devpy.toml").write_text(
        '[python]\nbase_conda_env = "base"\n',
    )

    assert (
        main(
            [
                "env",
                "--cwd",
                str(tmp_path),
                "--plain",
                "--show-home",
                "--show-tools",
                "--show-hints",
                "--abs-paths",
            ],
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "PATHS\n" in output
    assert f"  cwd  {tmp_path}" in output
    assert "TOOLS\n" in output
    assert "HINTS" in output


def test_cli_env_human_show_all_enables_optional_sections(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--show-all is a concise alias for all optional human env sections."""
    (tmp_path / "devpy.toml").write_text(
        '[python]\nbase_conda_env = "base"\n',
    )

    assert main(["env", "--cwd", str(tmp_path), "--plain", "--show-all"]) == 0

    output = capsys.readouterr().out
    assert "PATHS\n" in output
    assert "TOOLS\n" in output
    assert "HINTS" in output


def test_cli_env_verbose_uses_structured_sections(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verbose env diagnostics should use the same sectioned output grammar."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "example"\n')

    assert main(["env", "--cwd", str(tmp_path), "--plain", "--verbose"]) == 0

    output = capsys.readouterr().out
    assert "RUNTIME_DETAILS\n" in output
    assert "SHELL_ENV\n" in output
    assert "PROJECT_FILES\n" in output
    assert "TOOL_DETAILS\n" in output
    assert "RUNTIME implementation=" not in output
    assert "\nTOOL " not in output


def test_cli_env_compact_uses_one_line_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Env --compact uses dense rows while env default stays sectioned."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "example"\n')

    assert main(["env", "--cwd", str(tmp_path), "--plain", "--compact"]) == 0

    output = capsys.readouterr().out
    assert "ENV shell=" in output
    assert "PYTHON runtime=" in output
    assert "SHELL\n" not in output


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


def test_cli_human_non_compact_output_uses_sectioned_format(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--non-compact uses the sectioned repo summary."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    assert main(["--cwd", str(repo), "--plain", "--non-compact"]) == 0

    output = capsys.readouterr().out
    assert "REPO\n" in output
    assert "  name=repo" in output
    assert "STATE\n" in output
    assert "worktree=clean" in output


def test_cli_repo_worktrees_lists_linked_worktrees(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--worktrees shows the repo-family map without changing default output."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-b", "feature", str(linked))

    assert main(["repo", "--cwd", str(linked), "--plain"]) == 0
    default_output = capsys.readouterr().out
    assert "WORKTREES" not in default_output

    assert main(["repo", "--cwd", str(linked), "--plain", "--worktrees"]) == 0
    output = capsys.readouterr().out
    assert "WORKTREES count=2" in output
    assert str(repo) in output
    assert str(linked) in output
    assert "feature" in output
    assert "current" in output


def test_cli_repo_worktrees_github_streams_local_section(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--worktrees should be part of the local stream before GitHub calls."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    local_output_seen = ""

    def fake_collect_github_context(**_kwargs: object) -> tuple[GitHubContext, list]:
        nonlocal local_output_seen
        local_output_seen = capsys.readouterr().out
        return (
            GitHubContext(
                status="ok",
                pr_state="none",
                checks=RemoteCheckSummary(state="success", total=1, success=1),
            ),
            [],
        )

    monkeypatch.setattr(
        quick_status.cli,
        "collect_github_context",
        fake_collect_github_context,
    )

    assert main(["repo", "--cwd", str(repo), "--github", "--plain", "--worktrees"]) == 0

    capsys.readouterr()
    assert "WORKTREES count=1" in local_output_seen
    assert "PR " not in local_output_seen


def test_cli_repo_stashes_are_bounded_and_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--stashes shows bounded stash inventory without making it default."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    (repo / "README.md").write_text("# Test\n\none\n")
    _git(repo, "stash", "push", "-m", "first stash")
    (repo / "README.md").write_text("# Test\n\ntwo\n")
    _git(repo, "stash", "push", "-m", "second stash")

    assert main(["repo", "--cwd", str(repo), "--plain"]) == 0
    default_output = capsys.readouterr().out
    assert "STASHES" not in default_output
    assert "stash=2" in default_output

    assert (
        main(
            [
                "repo",
                "--cwd",
                str(repo),
                "--plain",
                "--stashes",
                "--stash-limit",
                "1",
            ],
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "STASHES count=2 detail=available" in output
    assert "stash@{0}" in output
    assert "stash@{1}" not in output
    assert "second stash" in output


def test_cli_repo_rejects_negative_stash_limit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stash detail limits should stay bounded."""
    with pytest.raises(SystemExit) as exc_info:
        main(["repo", "--cwd", str(tmp_path), "--stashes", "--stash-limit", "-1"])

    assert exc_info.value.code == 2
    assert "--stash-limit must be non-negative" in capsys.readouterr().err


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
    assert json.loads(output)["schema_version"] == "quick_status_repo_snapshot_v1"


def test_cli_github_human_prints_local_section_before_github(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Human GitHub mode should stream local repo facts before gh calls finish."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    local_output_seen = ""

    def fake_collect_github_context(**_kwargs: object) -> tuple[GitHubContext, list]:
        nonlocal local_output_seen
        local_output_seen = capsys.readouterr().out
        return (
            GitHubContext(
                status="ok",
                pr_state="none",
                checks=RemoteCheckSummary(state="success", total=1, success=1),
            ),
            [],
        )

    monkeypatch.setattr(
        quick_status.cli,
        "collect_github_context",
        fake_collect_github_context,
    )

    assert main(["--cwd", str(repo), "--github", "--plain"]) == 0

    github_output = capsys.readouterr().out
    assert "REPO repo " in local_output_seen
    assert "STATE clean" in local_output_seen
    assert "PR " not in local_output_seen
    assert "CI success" in github_output


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
