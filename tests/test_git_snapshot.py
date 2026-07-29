"""Tests for Git snapshot parsing and collection."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from quick_status.commands import CommandResult, run_command
from quick_status.git_snapshot import (
    collect_repo_snapshot,
    collect_stashes,
    github_repo_from_remotes,
    parse_porcelain_v2,
    parse_worktree_list,
    summarize_sync_state,
)
from quick_status.models import RemoteInfo

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_porcelain_v2_clean_synced_branch() -> None:
    """Parse a clean branch with an upstream."""
    branch, changes = parse_porcelain_v2(
        "\n".join(
            [
                "# branch.oid abcdef1234567890",
                "# branch.head main",
                "# branch.upstream origin/main",
                "# branch.ab +0 -0",
                "# stash 0",
            ],
        ),
    )

    assert branch.head == "main"
    assert branch.short_oid == "abcdef1"
    assert branch.sync_state == "synced"
    assert changes.worktree_state == "clean"
    assert changes.staged == 0
    assert changes.stash_count == 0
    assert changes.untracked == 0


def test_parse_porcelain_v2_dirty_counts() -> None:
    """Parse staged, unstaged, untracked, and conflict counts."""
    branch, changes = parse_porcelain_v2(
        "\n".join(
            [
                "# branch.oid abcdef1234567890",
                "# branch.head feature",
                "# branch.upstream origin/feature",
                "# branch.ab +2 -1",
                "# stash 3",
                "1 M. N... 100644 100644 100644 a b file_staged.py",
                "1 .M N... 100644 100644 100644 a b file_unstaged.py",
                "1 MM N... 100644 100644 100644 a b file_both.py",
                "? new_file.py",
                "u UU N... 100644 100644 100644 100644 a b c conflict.py",
            ],
        ),
    )

    assert branch.sync_state == "diverged"
    assert changes.worktree_state == "conflicted"
    assert changes.staged == 2
    assert changes.unstaged == 2
    assert changes.untracked == 1
    assert changes.conflicted == 1
    assert changes.stash_count == 3


def test_summarize_sync_state_cases() -> None:
    """Summarize common branch tracking states."""
    assert (
        summarize_sync_state(
            head="(detached)", upstream="origin/main", ahead=0, behind=0
        )
        == "detached"
    )
    assert summarize_sync_state(
        head="main", upstream=None, ahead=None, behind=None
    ) == ("no_upstream")
    assert summarize_sync_state(
        head="main", upstream="origin/main", ahead=1, behind=0
    ) == ("ahead")
    assert summarize_sync_state(
        head="main", upstream="origin/main", ahead=0, behind=1
    ) == ("behind")


def test_parse_porcelain_v2_detached_head() -> None:
    """Parse detached HEAD state."""
    branch, changes = parse_porcelain_v2(
        "\n".join(
            [
                "# branch.oid abcdef1234567890",
                "# branch.head (detached)",
            ],
        ),
    )

    assert branch.head == "(detached)"
    assert branch.sync_state == "detached"
    assert changes.worktree_state == "clean"


def test_github_repo_from_remotes_prefers_origin() -> None:
    """Extract GitHub owner/repo from SSH and HTTPS remotes."""
    assert (
        github_repo_from_remotes(
            [
                RemoteInfo(
                    name="origin",
                    fetch_url="git@github.com:alik-git/quick-status.git",
                ),
            ],
        )
        == "alik-git/quick-status"
    )
    assert (
        github_repo_from_remotes(
            [
                RemoteInfo(
                    name="upstream",
                    fetch_url="https://github.com/example/project.git",
                ),
            ],
        )
        == "example/project"
    )


def test_parse_worktree_list_covers_status_flags() -> None:
    """Parse linked, detached, bare, and prunable worktree entries."""
    entries = parse_worktree_list(
        "\n".join(
            [
                "worktree /repo",
                "HEAD aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "branch refs/heads/main",
                "",
                "worktree /repo-linked",
                "HEAD bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "detached",
                "",
                "worktree /repo-bare",
                "bare",
                "",
                "worktree /repo-old",
                "HEAD cccccccccccccccccccccccccccccccccccccccc",
                "branch refs/heads/feature",
                "prunable gitdir file points to non-existent location",
            ],
        ),
    )

    assert [entry.path for entry in entries] == [
        "/repo",
        "/repo-linked",
        "/repo-bare",
        "/repo-old",
    ]
    assert entries[0].branch == "main"
    assert entries[1].detached is True
    assert entries[2].bare is True
    assert entries[3].branch == "feature"
    assert entries[3].prunable is True
    assert all(entry.is_current is False for entry in entries)


def test_collect_repo_snapshot_clean_repo(tmp_path: Path) -> None:
    """Collect a real clean repository snapshot without network access."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")

    snapshot = collect_repo_snapshot(repo)

    assert snapshot.repo.root == str(repo)
    assert snapshot.branch.head in {"main", "master"}
    assert snapshot.summary.worktree_state == "clean"
    assert snapshot.summary.sync_state == "no_upstream"
    assert snapshot.github.status == "not_requested"


def test_collect_repo_snapshot_marks_current_worktree(tmp_path: Path) -> None:
    """The resolved current repo root should be marked in the worktree list."""
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

    snapshot = collect_repo_snapshot(linked)

    current_entries = [
        entry for entry in snapshot.worktree.worktrees if entry.is_current
    ]
    assert len(current_entries) == 1
    assert current_entries[0].path == str(linked)
    assert current_entries[0].branch == "feature"
    assert snapshot.worktree.count == 2


def test_collect_stashes_details_are_bounded_and_non_fatal(tmp_path: Path) -> None:
    """Stash detail failures should degrade without failing the repo snapshot."""

    def fake_git(args: list[str], *, timeout_s: float = 3.0) -> CommandResult:
        del timeout_s
        if args[:2] == ["stash", "list"]:
            return CommandResult(
                args=("git", *args),
                cwd=tmp_path,
                exit_code=0,
                stdout=(
                    "stash@{0}\x1fOn main: first stash\n"
                    "stash@{1}\x1fOn feature: second stash\n"
                ),
                stderr="",
            )
        if args == ["stash", "show", "--name-only", "stash@{0}"]:
            return CommandResult(
                args=("git", *args),
                cwd=tmp_path,
                exit_code=0,
                stdout="README.md\n",
                stderr="",
            )
        if args == ["stash", "show", "--name-only", "stash@{1}"]:
            return CommandResult(
                args=("git", *args),
                cwd=tmp_path,
                exit_code=1,
                stdout="",
                stderr="unavailable",
            )
        raise AssertionError(args)

    count_only = collect_stashes(
        fake_git,
        stash_count=None,
        include_details=False,
        limit=5,
    )
    detailed = collect_stashes(
        fake_git,
        stash_count=None,
        include_details=True,
        limit=2,
    )

    assert count_only.count == 2
    assert count_only.detail_status == "not_requested"
    assert count_only.entries == []
    assert detailed.count == 2
    assert detailed.detail_status == "partial"
    assert detailed.entries[0].branch == "main"
    assert detailed.entries[0].file_count == 1
    assert detailed.entries[1].branch == "feature"
    assert detailed.entries[1].file_count is None
    assert detailed.entries[1].detail_status == "unavailable"


def test_collect_stash_details_runs_independent_probes_concurrently(
    tmp_path: Path,
) -> None:
    """Independent stash file-count probes should enter the pool together."""
    barrier = threading.Barrier(4)

    def fake_git(args: list[str], *, timeout_s: float = 3.0) -> CommandResult:
        """Return four stashes and require concurrent detail probes."""
        del timeout_s
        if args[:2] == ["stash", "list"]:
            return CommandResult(
                args=("git", *args),
                cwd=tmp_path,
                exit_code=0,
                stdout="\n".join(
                    f"stash@{{{index}}}\x1fOn main: stash {index}" for index in range(4)
                ),
                stderr="",
            )
        if args[:3] == ["stash", "show", "--name-only"]:
            barrier.wait(timeout=1)
            return CommandResult(
                args=("git", *args),
                cwd=tmp_path,
                exit_code=0,
                stdout="README.md\n",
                stderr="",
            )
        raise AssertionError(args)

    detailed = collect_stashes(
        fake_git,
        stash_count=4,
        include_details=True,
        limit=4,
    )

    assert detailed.detail_status == "available"
    assert len(detailed.entries) == 4


def test_collect_repo_snapshot_ahead_of_upstream(tmp_path: Path) -> None:
    """Collect ahead/synced state from a local bare remote."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "clone", str(remote), str(work))
    _git(work, "config", "user.name", "Test User")
    _git(work, "config", "user.email", "test@example.com")
    (work / "file.txt").write_text("one\n")
    _git(work, "add", "file.txt")
    _git(work, "commit", "-m", "initial")
    _git(work, "push", "-u", "origin", "HEAD")
    (work / "file.txt").write_text("two\n")
    _git(work, "commit", "-am", "second")

    snapshot = collect_repo_snapshot(work)

    assert snapshot.branch.upstream in {"origin/main", "origin/master"}
    assert snapshot.branch.ahead == 1
    assert snapshot.branch.behind == 0
    assert snapshot.summary.sync_state == "ahead"


def test_collect_repo_snapshot_detached_head(tmp_path: Path) -> None:
    """Collect detached HEAD state from a real repository."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    result = run_command(["git", "rev-parse", "HEAD"], cwd=repo, timeout_s=10.0)
    assert result.ok, result.stderr or result.stdout
    _git(repo, "checkout", result.stdout.strip())

    snapshot = collect_repo_snapshot(repo)

    assert snapshot.branch.head == "(detached)"
    assert snapshot.summary.sync_state == "detached"


def test_collect_repo_snapshot_submodule_present(tmp_path: Path) -> None:
    """Collect submodule summary when `.gitmodules` exists."""
    submodule_repo = tmp_path / "submodule"
    submodule_repo.mkdir()
    _git(submodule_repo, "init")
    _git(submodule_repo, "config", "user.name", "Test User")
    _git(submodule_repo, "config", "user.email", "test@example.com")
    (submodule_repo / "file.txt").write_text("sub\n")
    _git(submodule_repo, "add", "file.txt")
    _git(submodule_repo, "commit", "-m", "submodule initial")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(submodule_repo),
        "deps/submodule",
    )
    _git(repo, "commit", "-am", "add submodule")

    snapshot = collect_repo_snapshot(repo)

    assert snapshot.submodules.present is True
    assert snapshot.submodules.total == 1
    assert snapshot.submodules.clean == 1


def _git(cwd: Path, *args: str) -> None:
    result = run_command(["git", *args], cwd=cwd, timeout_s=10.0)
    assert result.ok, result.stderr or result.stdout
