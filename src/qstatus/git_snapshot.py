"""Git repository snapshot collection and parsing."""

from __future__ import annotations

import re
from pathlib import Path

from qstatus.commands import CommandResult, run_command
from qstatus.models import (
    SCHEMA_VERSION,
    BranchState,
    ChangeSummary,
    CommandRecord,
    GitHubContext,
    RemoteInfo,
    RepoIdentity,
    RepoSnapshot,
    RepoSummary,
    StashEntry,
    StashState,
    SubmoduleSummary,
    WorktreeEntry,
    WorktreeState,
)


class RepoSnapshotError(RuntimeError):
    """Raised when qstatus cannot create a repo snapshot."""


_GITHUB_REMOTE_PATTERNS = (
    re.compile(r"^git@github\.com:(?P<repo>[^/]+/[^.]+?)(?:\.git)?$"),
    re.compile(r"^https://github\.com/(?P<repo>[^/]+/[^.]+?)(?:\.git)?/?$"),
    re.compile(r"^ssh://git@github\.com/(?P<repo>[^/]+/[^.]+?)(?:\.git)?/?$"),
)


def collect_repo_snapshot(
    cwd: Path,
    *,
    include_github: bool = False,
    include_commands: bool = False,
    include_stashes: bool = False,
    stash_limit: int = 5,
) -> RepoSnapshot:
    """Collect a read-only local Git snapshot for a repository."""
    command_records: list[CommandRecord] = []

    def git(args: list[str], *, timeout_s: float = 3.0) -> CommandResult:
        result = run_command(["git", *args], cwd=cwd, timeout_s=timeout_s)
        if include_commands:
            command_records.append(result.evidence())
        return result

    root_result = git(["rev-parse", "--show-toplevel"])
    if root_result.unavailable:
        raise RepoSnapshotError("git is not installed or not on PATH")
    if not root_result.ok:
        detail = root_result.stderr.strip() or root_result.stdout.strip()
        raise RepoSnapshotError(f"not a git worktree: {cwd} ({detail})")
    root = Path(root_result.stdout.strip()).resolve()

    git_dir_result = git(["rev-parse", "--git-dir"])
    git_dir = git_dir_result.stdout.strip() if git_dir_result.ok else ""
    if git_dir:
        git_dir_path = Path(git_dir)
        if not git_dir_path.is_absolute():
            git_dir = str((root / git_dir_path).resolve())

    status_result = git(["status", "--porcelain=v2", "--branch", "--show-stash"])
    if not status_result.ok:
        detail = status_result.stderr.strip() or status_result.stdout.strip()
        raise RepoSnapshotError(f"git status failed: {detail}")
    branch, changes = parse_porcelain_v2(status_result.stdout)

    remotes_result = git(["remote", "-v"])
    remotes = parse_remotes(remotes_result.stdout if remotes_result.ok else "")

    commit_subject_result = git(["log", "-1", "--format=%s"])
    commit_subject = (
        commit_subject_result.stdout.strip() if commit_subject_result.ok else None
    )
    branch = BranchState(
        head=branch.head,
        oid=branch.oid,
        short_oid=branch.short_oid,
        upstream=branch.upstream,
        ahead=branch.ahead,
        behind=branch.behind,
        sync_state=branch.sync_state,
        commit_subject=commit_subject,
    )

    diff_result = git(["diff", "--shortstat"], timeout_s=5.0)
    cached_diff_result = git(["diff", "--cached", "--shortstat"], timeout_s=5.0)
    changes = ChangeSummary(
        staged=changes.staged,
        unstaged=changes.unstaged,
        untracked=changes.untracked,
        conflicted=changes.conflicted,
        stash_count=changes.stash_count,
        worktree_state=changes.worktree_state,
        tracked_entries=changes.tracked_entries,
        diff_shortstat=diff_result.stdout.strip() if diff_result.ok else None,
        cached_diff_shortstat=(
            cached_diff_result.stdout.strip() if cached_diff_result.ok else None
        ),
    )

    worktree_result = git(["worktree", "list", "--porcelain"])
    worktrees = (
        parse_worktree_list(worktree_result.stdout) if worktree_result.ok else []
    )
    worktree = WorktreeState(
        current_path=str(root),
        worktrees=mark_current_worktree(worktrees, root),
        count=len(worktrees),
    )

    stashes = collect_stashes(
        git,
        stash_count=changes.stash_count,
        include_details=include_stashes,
        limit=stash_limit,
    )
    if stashes.count != changes.stash_count:
        changes = ChangeSummary(
            staged=changes.staged,
            unstaged=changes.unstaged,
            untracked=changes.untracked,
            conflicted=changes.conflicted,
            stash_count=stashes.count,
            worktree_state=changes.worktree_state,
            tracked_entries=changes.tracked_entries,
            diff_shortstat=changes.diff_shortstat,
            cached_diff_shortstat=changes.cached_diff_shortstat,
        )
    submodules = collect_submodules(root, git)
    github_repo = github_repo_from_remotes(remotes)
    repo = RepoIdentity(
        root=str(root),
        git_dir=git_dir,
        name=root.name,
        remotes=remotes,
        github_repo=github_repo,
    )
    github = GitHubContext(
        status="not_requested" if not include_github else "unavailable",
        repo=github_repo,
        pr_state="unknown" if include_github else "none",
    )
    summary = RepoSummary(
        sync_state=branch.sync_state,
        worktree_state=changes.worktree_state,
        pr_state=github.pr_state,
        remote_check_state="unknown" if include_github else "none",
    )
    return RepoSnapshot(
        schema_version=SCHEMA_VERSION,
        repo=repo,
        branch=branch,
        changes=changes,
        worktree=worktree,
        stashes=stashes,
        submodules=submodules,
        github=github,
        summary=summary,
        commands=command_records,
    )


def parse_porcelain_v2(output: str) -> tuple[BranchState, ChangeSummary]:
    """Parse `git status --porcelain=v2 --branch --show-stash` output."""
    oid: str | None = None
    head = "unknown"
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    stash_count: int | None = None
    staged = 0
    unstaged = 0
    untracked = 0
    conflicted = 0
    tracked_entries = 0

    for raw_line in output.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            continue
        if line.startswith("# "):
            key, _, value = line[2:].partition(" ")
            if key == "branch.oid":
                oid = None if value == "(initial)" else value
            elif key == "branch.head":
                head = value
            elif key == "branch.upstream":
                upstream = value
            elif key == "branch.ab":
                ahead, behind = _parse_ahead_behind(value)
            elif key == "stash":
                stash_count = _parse_int(value)
            continue
        kind = line[0]
        if kind == "?":
            untracked += 1
            continue
        if kind == "u":
            conflicted += 1
            tracked_entries += 1
            continue
        if kind in {"1", "2"}:
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            xy = parts[1]
            tracked_entries += 1
            if len(xy) >= 2:
                if "U" in xy or xy in {"AA", "DD"}:
                    conflicted += 1
                else:
                    if xy[0] != ".":
                        staged += 1
                    if xy[1] != ".":
                        unstaged += 1

    sync_state = summarize_sync_state(
        head=head,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
    )
    worktree_state = summarize_worktree_state(
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        conflicted=conflicted,
    )
    branch = BranchState(
        head=head,
        oid=oid,
        short_oid=oid[:7] if oid else None,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        sync_state=sync_state,
    )
    changes = ChangeSummary(
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        conflicted=conflicted,
        stash_count=stash_count,
        worktree_state=worktree_state,
        tracked_entries=tracked_entries,
    )
    return branch, changes


def summarize_sync_state(
    *,
    head: str,
    upstream: str | None,
    ahead: int | None,
    behind: int | None,
) -> str:
    """Summarize branch/upstream sync state without making workflow judgments."""
    if head == "(detached)":
        return "detached"
    if not upstream:
        return "no_upstream"
    if ahead is None or behind is None:
        return "unknown"
    if ahead == 0 and behind == 0:
        return "synced"
    if ahead > 0 and behind > 0:
        return "diverged"
    if ahead > 0:
        return "ahead"
    if behind > 0:
        return "behind"
    return "unknown"


def summarize_worktree_state(
    *,
    staged: int,
    unstaged: int,
    untracked: int,
    conflicted: int,
) -> str:
    """Summarize local worktree state without deciding readiness."""
    if conflicted:
        return "conflicted"
    if staged or unstaged or untracked:
        return "dirty"
    return "clean"


def parse_remotes(output: str) -> list[RemoteInfo]:
    """Parse `git remote -v` output."""
    remotes: dict[str, RemoteInfo] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        name, url, direction = parts[:3]
        current = remotes.get(name, RemoteInfo(name=name))
        if direction == "(fetch)":
            current = RemoteInfo(name=name, fetch_url=url, push_url=current.push_url)
        elif direction == "(push)":
            current = RemoteInfo(name=name, fetch_url=current.fetch_url, push_url=url)
        remotes[name] = current
    return [remotes[name] for name in sorted(remotes)]


def github_repo_from_remotes(remotes: list[RemoteInfo]) -> str | None:
    """Return `owner/repo` for the first GitHub remote URL if available."""
    urls: list[str] = []
    for remote in remotes:
        if remote.name == "origin":
            urls.extend(url for url in (remote.fetch_url, remote.push_url) if url)
    for remote in remotes:
        urls.extend(url for url in (remote.fetch_url, remote.push_url) if url)
    for url in urls:
        for pattern in _GITHUB_REMOTE_PATTERNS:
            match = pattern.match(url)
            if match:
                return match.group("repo")
    return None


def parse_worktree_list(output: str) -> list[WorktreeEntry]:
    """Parse `git worktree list --porcelain` output."""
    entries: list[WorktreeEntry] = []
    current: dict[str, str | bool] = {}

    def flush() -> None:
        if "worktree" not in current:
            current.clear()
            return
        head_value = current.get("HEAD")
        branch_value = current.get("branch")
        entries.append(
            WorktreeEntry(
                path=str(current["worktree"]),
                head=head_value if isinstance(head_value, str) else None,
                branch=(
                    _short_branch(branch_value)
                    if isinstance(branch_value, str)
                    else None
                ),
                bare=bool(current.get("bare", False)),
                detached=bool(current.get("detached", False)),
                prunable=bool(current.get("prunable", False)),
            ),
        )
        current.clear()

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        key, _, value = line.partition(" ")
        if key == "worktree" and current:
            flush()
        if value:
            current[key] = value
        else:
            current[key] = True
    flush()
    return entries


def mark_current_worktree(
    worktrees: list[WorktreeEntry],
    current_path: Path,
) -> list[WorktreeEntry]:
    """Mark the current worktree entry from the resolved repo root."""
    current = str(current_path.resolve())
    return [
        WorktreeEntry(
            path=entry.path,
            head=entry.head,
            branch=entry.branch,
            bare=entry.bare,
            detached=entry.detached,
            prunable=entry.prunable,
            is_current=str(Path(entry.path).resolve()) == current,
        )
        for entry in worktrees
    ]


def collect_stashes(
    git_runner,
    *,
    stash_count: int | None,
    include_details: bool,
    limit: int,
) -> StashState:
    """Collect bounded stash details only when explicitly requested."""
    if not include_details and stash_count is not None:
        return StashState(count=stash_count)

    result = git_runner(["stash", "list", "--format=%gd%x1f%gs"], timeout_s=3.0)
    if not result.ok:
        return StashState(count=stash_count, detail_status="unavailable")

    stash_lines = [line for line in result.stdout.splitlines() if line.strip()]
    count = len(stash_lines)
    if not include_details:
        return StashState(count=count)
    if limit <= 0:
        return StashState(count=count, detail_status="available")

    entries: list[StashEntry] = []
    detail_status = "available"
    for line in stash_lines[:limit]:
        ref, _, subject = line.partition("\x1f")
        if not ref:
            continue
        file_count, entry_status = _stash_file_count(git_runner, ref)
        if entry_status != "available":
            detail_status = "partial"
        entries.append(
            StashEntry(
                ref=ref,
                index=_stash_index(ref),
                subject=subject,
                branch=_stash_branch(subject),
                file_count=file_count,
                detail_status=entry_status,
            ),
        )
    return StashState(
        count=count,
        detail_status=detail_status,
        entries=entries,
    )


def collect_submodules(root: Path, git_runner) -> SubmoduleSummary:
    """Collect submodule summary only when `.gitmodules` exists."""
    if not (root / ".gitmodules").exists():
        return SubmoduleSummary(present=False)
    result = git_runner(["submodule", "status", "--recursive"], timeout_s=5.0)
    if not result.ok:
        return SubmoduleSummary(present=True, unknown=1)

    total = clean = changed = uninitialized = conflicted = unknown = 0
    for line in result.stdout.splitlines():
        if not line:
            continue
        total += 1
        status = line[0]
        if status == " ":
            clean += 1
        elif status == "+":
            changed += 1
        elif status == "-":
            uninitialized += 1
        elif status == "U":
            conflicted += 1
        else:
            unknown += 1
    return SubmoduleSummary(
        present=True,
        total=total,
        clean=clean,
        changed=changed,
        uninitialized=uninitialized,
        conflicted=conflicted,
        unknown=unknown,
    )


def _parse_ahead_behind(value: str) -> tuple[int | None, int | None]:
    ahead = behind = None
    for token in value.split():
        if token.startswith("+"):
            ahead = _parse_int(token[1:])
        elif token.startswith("-"):
            behind = _parse_int(token[1:])
    return ahead, behind


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _short_branch(value: str) -> str:
    return value.removeprefix("refs/heads/")


def _stash_file_count(git_runner, ref: str) -> tuple[int | None, str]:
    result = git_runner(["stash", "show", "--name-only", ref], timeout_s=3.0)
    if not result.ok:
        return None, "unavailable"
    files = [line for line in result.stdout.splitlines() if line.strip()]
    return len(files), "available"


def _stash_index(ref: str) -> int | None:
    match = re.fullmatch(r"stash@\{(?P<index>\d+)\}", ref)
    return int(match.group("index")) if match else None


def _stash_branch(subject: str) -> str | None:
    match = re.match(r"^(?:WIP on|On) (?P<branch>[^:]+):", subject)
    return match.group("branch") if match else None
