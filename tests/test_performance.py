"""Performance regression tests for quick_status fast paths."""

from __future__ import annotations

import stat
import threading
import time
from typing import TYPE_CHECKING

from quick_status.cli import main
from quick_status.commands import CommandResult, run_command
from quick_status.env_render import render_env_human
from quick_status.env_snapshot import collect_env_snapshot
from quick_status.git_snapshot import collect_repo_snapshot

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


ENV_COLLECT_BUDGET_S = 0.08
ENV_RENDER_BUDGET_S = 0.03
ENV_MAIN_BUDGET_S = 0.12


def test_env_default_fast_path_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default env output should stay fast and avoid optional version probes."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "demo"\n')

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python", "python3", "uv", "conda", "veneer", "pip", "pip3"):
        _slow_version_executable(bin_dir / name)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}

    collect_start = time.perf_counter()
    snapshot = collect_env_snapshot(project, env=env)
    collect_s = time.perf_counter() - collect_start

    render_start = time.perf_counter()
    render_env_human(snapshot, color=False)
    render_s = time.perf_counter() - render_start

    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("HOME", str(tmp_path))
    main_start = time.perf_counter()
    assert main(["env", "--cwd", str(project), "--plain"]) == 0
    main_s = time.perf_counter() - main_start
    capsys.readouterr()

    breakdown = (
        f"collect={collect_s:.4f}s render={render_s:.4f}s main={main_s:.4f}s; "
        "default quick_status env should use path probes only. "
        "If this fails, check for accidental version subprocesses or broad scans."
    )
    assert collect_s < ENV_COLLECT_BUDGET_S, breakdown
    assert render_s < ENV_RENDER_BUDGET_S, breakdown
    assert main_s < ENV_MAIN_BUDGET_S, breakdown


def test_repo_compact_path_uses_three_git_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compact local collection should keep its deterministic three-call plan."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    calls: list[list[str]] = []

    def recording_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float = 3.0,
    ) -> CommandResult:
        """Record and execute one real Git command."""
        calls.append(args)
        return run_command(args, cwd=cwd, timeout_s=timeout_s)

    monkeypatch.setattr(
        "quick_status.git_snapshot.run_command",
        recording_run_command,
    )

    snapshot = collect_repo_snapshot(
        repo,
        include_details=False,
        include_worktrees=False,
    )

    assert snapshot.repo.root == str(repo)
    assert [args[1] for args in calls] == ["rev-parse", "status", "remote"]


def test_env_verbose_version_probes_run_concurrently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seven version probes should enter the worker pool together."""
    project = tmp_path / "project"
    project.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python", "python3", "git", "uv", "conda", "veneer", "pip", "pip3"):
        _slow_version_executable(bin_dir / name)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}
    barrier = threading.Barrier(7)

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float = 3.0,
    ) -> CommandResult:
        """Require every version subprocess to overlap."""
        del timeout_s
        if args[-1] == "--version":
            barrier.wait(timeout=1)
            return CommandResult(
                args=tuple(args),
                cwd=cwd,
                exit_code=0,
                stdout="fake 1.0\n",
                stderr="",
            )
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=1,
            stdout="",
            stderr="not a repo",
        )

    monkeypatch.setattr(
        "quick_status.env_snapshot.run_command",
        fake_run_command,
    )
    snapshot = collect_env_snapshot(
        project,
        include_commands=True,
        probe_versions=True,
        env=env,
    )

    assert len(snapshot.commands) == 8


def _slow_version_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nsleep 0.1\necho slow-version\n")
    path.chmod(stat.S_IRWXU)


def _git(repo: Path, *args: str) -> None:
    result = run_command(["git", *args], cwd=repo, timeout_s=10)
    assert result.ok, result.stderr or result.stdout
