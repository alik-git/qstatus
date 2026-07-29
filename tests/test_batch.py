"""Tests for explicit multi-repository and workset snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quick_status.batch import collect_repo_batch, discover_workset_repositories
from quick_status.cli import main
from quick_status.commands import run_command

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_collect_repo_batch_preserves_input_order(tmp_path: Path) -> None:
    """Concurrent collection should preserve the caller's repository order."""
    second = _repo(tmp_path / "second")
    first = _repo(tmp_path / "first")

    snapshot = collect_repo_batch([second, first], workers=2)

    assert [item.path for item in snapshot.items] == [str(second), str(first)]
    assert [item.snapshot.repo.name for item in snapshot.items if item.snapshot] == [
        "second",
        "first",
    ]


def test_cli_repos_json_keeps_errors_as_items(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Batch JSON should retain valid snapshots and invalid targets together."""
    repo = _repo(tmp_path / "repo")
    missing = tmp_path / "missing"

    assert main(["repos", str(repo), str(missing), "--json"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "quick_status_repo_batch_v1"
    assert payload["items"][0]["status"] == "ok"
    assert payload["items"][1]["status"] == "error"
    assert "does not exist" in payload["items"][1]["error"]


def test_workset_discovers_only_immediate_git_children(tmp_path: Path) -> None:
    """Workset discovery should be shallow and deterministic."""
    workset = tmp_path / "workset"
    workset.mkdir()
    beta = _repo(workset / "beta")
    alpha = _repo(workset / "alpha")
    ignored = workset / "notes"
    ignored.mkdir()
    nested = ignored / "nested"
    _repo(nested)

    repositories = discover_workset_repositories(workset)

    assert repositories == [alpha, beta]


def test_cli_workset_human_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The workset command should render one compact row per immediate repo."""
    workset = tmp_path / "workset"
    workset.mkdir()
    _repo(workset / "alpha")
    _repo(workset / "beta")

    assert main(["workset", str(workset), "--plain", "--workers", "2"]) == 0

    output = capsys.readouterr().out
    assert "REPO alpha" in output
    assert "REPO beta" in output
    assert output.index("REPO alpha") < output.index("REPO beta")


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "user.email", "test@example.com")
    (path / "README.md").write_text("# Test\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "initial")
    return path


def _git(repo: Path, *args: str) -> None:
    result = run_command(["git", *args], cwd=repo, timeout_s=10)
    assert result.ok, result.stderr or result.stdout
