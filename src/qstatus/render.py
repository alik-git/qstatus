"""Human and JSON renderers for qstatus repo snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qstatus.models import RemoteInfo, RepoSnapshot, SubmoduleSummary


def render_json(snapshot: RepoSnapshot, *, verbose: bool = False) -> str:
    """Render a repo snapshot as stable JSON."""
    return json.dumps(
        snapshot.to_dict(include_commands=verbose),
        indent=2,
        sort_keys=True,
    )


def render_human(snapshot: RepoSnapshot, *, verbose: bool = False) -> str:
    """Render a compact human-readable repo snapshot."""
    branch = snapshot.branch
    changes = snapshot.changes
    github = snapshot.github
    submodules = snapshot.submodules
    remote = _origin_or_first_remote(snapshot)
    upstream = branch.upstream or "no-upstream"
    commit = branch.short_oid or "no-commit"
    stash = changes.stash_count if changes.stash_count is not None else "unknown"

    lines = [
        f"REPO {snapshot.repo.name} {snapshot.repo.root}",
        (
            f"BRANCH {branch.head} {commit} {upstream} {branch.sync_state} "
            f"ahead={branch.ahead if branch.ahead is not None else '?'} "
            f"behind={branch.behind if branch.behind is not None else '?'}"
        ),
        (
            f"STATE {changes.worktree_state} staged={changes.staged} "
            f"unstaged={changes.unstaged} untracked={changes.untracked} "
            f"conflicts={changes.conflicted} stash={stash}"
        ),
        f"REMOTE {_format_remote(remote)}",
        f"SUBMODULES {_format_submodules(submodules)}",
        f"PR {_format_pr(snapshot)}",
        f"CI {_format_ci(snapshot)}",
    ]
    if github.release is not None:
        release = github.release
        exists = (
            "yes" if release.exists else "no" if release.exists is False else "unknown"
        )
        release_name = release.tag or release.version or "unknown"
        lines.append(f"RELEASE {release_name} exists={exists}")
    if verbose:
        if branch.commit_subject:
            lines.append(f"COMMIT {branch.commit_subject}")
        lines.append(f"WORKTREES count={snapshot.worktree.count}")
        if changes.diff_shortstat:
            lines.append(f"DIFF {changes.diff_shortstat}")
        if changes.cached_diff_shortstat:
            lines.append(f"CACHED_DIFF {changes.cached_diff_shortstat}")
        if snapshot.github.error:
            lines.append(f"GITHUB_ERROR {snapshot.github.error}")
        for command in snapshot.commands:
            if command.timed_out:
                status: int | str | None = "timeout"
            elif command.unavailable:
                status = "unavailable"
            else:
                status = command.exit_code
            lines.append(f"CMD {status} {' '.join(command.args)}")
    return "\n".join(lines)


def _origin_or_first_remote(snapshot: RepoSnapshot) -> RemoteInfo | None:
    for remote in snapshot.repo.remotes:
        if remote.name == "origin":
            return remote
    return snapshot.repo.remotes[0] if snapshot.repo.remotes else None


def _format_remote(remote: RemoteInfo | None) -> str:
    if remote is None:
        return "none"
    url = remote.fetch_url or remote.push_url or "unknown-url"
    return f"{remote.name} {url}"


def _format_submodules(submodules: SubmoduleSummary) -> str:
    if not submodules.present:
        return "none"
    return (
        f"total={submodules.total} clean={submodules.clean} "
        f"changed={submodules.changed} uninitialized={submodules.uninitialized} "
        f"conflicts={submodules.conflicted} unknown={submodules.unknown}"
    )


def _format_pr(snapshot: RepoSnapshot) -> str:
    github = snapshot.github
    if github.status == "not_requested":
        return "not-requested"
    if github.status == "unavailable":
        return f"unavailable {github.error or ''}".strip()
    if github.pull_request is None:
        return "none"
    pr = github.pull_request
    draft = " draft" if pr.is_draft else ""
    return f"#{pr.number}{draft} {pr.state} {pr.url}"


def _format_ci(snapshot: RepoSnapshot) -> str:
    github = snapshot.github
    if github.status == "not_requested":
        return "not-requested"
    if github.status == "unavailable":
        return "unknown"
    checks = github.checks
    if checks is None:
        return "unknown"
    return (
        f"{checks.state} total={checks.total} success={checks.success} "
        f"failure={checks.failure} pending={checks.pending} running={checks.running} "
        f"skipped={checks.skipped} unknown={checks.unknown}"
    )
