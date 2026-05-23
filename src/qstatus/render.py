"""Human and JSON renderers for qstatus repo snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qstatus.models import RemoteInfo, RepoSnapshot, SubmoduleSummary


_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[38;2;224;108;117m"
_GREEN = "\033[38;2;152;195;121m"
_AMBER = "\033[38;2;229;192;123m"
_BLUE = "\033[38;2;97;175;239m"
_PURPLE = "\033[38;2;198;120;221m"
_COMMENT_GREEN = "\033[38;2;161;216;183m"
_VARIABLE = "\033[38;2;223;223;223m"
_MUTED = "\033[38;2;171;178;191m"
_NUMBER = "\033[38;2;209;154;102m"


def render_json(snapshot: RepoSnapshot, *, verbose: bool = False) -> str:
    """Render a repo snapshot as stable JSON."""
    return json.dumps(
        snapshot.to_dict(include_commands=verbose),
        indent=2,
        sort_keys=True,
    )


def render_human(
    snapshot: RepoSnapshot,
    *,
    verbose: bool = False,
    color: bool = False,
) -> str:
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
        (
            f"{_label('REPO', color)} {_name(snapshot.repo.name, color)} "
            f"{_variable(snapshot.repo.root, color)}"
        ),
        (
            f"{_label('BRANCH', color)} {_name(branch.head, color)} "
            f"{_muted(commit, color)} {_muted(upstream, color)} "
            f"{_state(branch.sync_state, color)} "
            f"{_kv('ahead', branch.ahead, color)} "
            f"{_kv('behind', branch.behind, color)}"
        ),
        (
            f"{_label('STATE', color)} {_state(changes.worktree_state, color)} "
            f"{_kv('staged', changes.staged, color)} "
            f"{_kv('unstaged', changes.unstaged, color)} "
            f"{_kv('untracked', changes.untracked, color)} "
            f"{_kv('conflicts', changes.conflicted, color)} "
            f"{_kv('stash', stash, color)}"
        ),
        f"{_label('REMOTE', color)} {_format_remote(remote, color=color)}",
        f"{_label('SUBMODULES', color)} {_format_submodules(submodules, color=color)}",
        f"{_label('PR', color)} {_format_pr(snapshot, color=color)}",
        f"{_label('CI', color)} {_format_ci(snapshot, color=color)}",
    ]
    if github.release is not None:
        release = github.release
        exists = (
            "yes" if release.exists else "no" if release.exists is False else "unknown"
        )
        release_name = release.tag or release.version or "unknown"
        lines.append(
            f"{_label('RELEASE', color)} {_name(release_name, color)} "
            f"exists={_state(exists, color)}",
        )
    if verbose:
        if branch.commit_subject:
            lines.append(f"{_label('COMMIT', color)} {branch.commit_subject}")
        worktree_count = _kv("count", snapshot.worktree.count, color)
        lines.append(
            f"{_label('WORKTREES', color)} {worktree_count}",
        )
        if changes.diff_shortstat:
            lines.append(f"{_label('DIFF', color)} {changes.diff_shortstat}")
        if changes.cached_diff_shortstat:
            lines.append(
                f"{_label('CACHED_DIFF', color)} {changes.cached_diff_shortstat}",
            )
        if snapshot.github.error:
            lines.append(f"{_label('GITHUB_ERROR', color)} {snapshot.github.error}")
        for command in snapshot.commands:
            if command.timed_out:
                status: int | str | None = "timeout"
            elif command.unavailable:
                status = "unavailable"
            else:
                status = command.exit_code
            lines.append(
                f"{_label('CMD', color)} {_state(str(status), color)} "
                f"{' '.join(command.args)}",
            )
    return "\n".join(lines)


def _origin_or_first_remote(snapshot: RepoSnapshot) -> RemoteInfo | None:
    for remote in snapshot.repo.remotes:
        if remote.name == "origin":
            return remote
    return snapshot.repo.remotes[0] if snapshot.repo.remotes else None


def _format_remote(remote: RemoteInfo | None, *, color: bool) -> str:
    if remote is None:
        return _state("none", color)
    url = remote.fetch_url or remote.push_url or "unknown-url"
    return f"{_name(remote.name, color)} {_variable(url, color)}"


def _format_submodules(submodules: SubmoduleSummary, *, color: bool) -> str:
    if not submodules.present:
        return _state("none", color)
    state = (
        "clean"
        if submodules.changed == 0
        and submodules.uninitialized == 0
        and submodules.conflicted == 0
        and submodules.unknown == 0
        else "dirty"
    )
    return (
        f"{_state(state, color)} {_kv('total', submodules.total, color)} "
        f"{_kv('clean', submodules.clean, color)} "
        f"{_kv('changed', submodules.changed, color)} "
        f"{_kv('uninitialized', submodules.uninitialized, color)} "
        f"{_kv('conflicts', submodules.conflicted, color)} "
        f"{_kv('unknown', submodules.unknown, color)}"
    )


def _format_pr(snapshot: RepoSnapshot, *, color: bool) -> str:
    github = snapshot.github
    if github.status == "not_requested":
        return _state("not-requested", color)
    if github.status == "unavailable":
        return f"{_state('unavailable', color)} {github.error or ''}".strip()
    if github.pull_request is None:
        return _state("none", color)
    pr = github.pull_request
    draft = " draft" if pr.is_draft else ""
    return (
        f"{_name(f'#{pr.number}{draft}', color)} {_state(pr.state, color)} "
        f"{_variable(pr.url, color)}"
    )


def _format_ci(snapshot: RepoSnapshot, *, color: bool) -> str:
    github = snapshot.github
    if github.status == "not_requested":
        return _state("not-requested", color)
    if github.status == "unavailable":
        return _state("unknown", color)
    checks = github.checks
    if checks is None:
        return _state("unknown", color)
    return (
        f"{_state(checks.state, color)} {_kv('total', checks.total, color)} "
        f"{_kv('success', checks.success, color)} "
        f"{_kv('failure', checks.failure, color)} "
        f"{_kv('pending', checks.pending, color)} "
        f"{_kv('running', checks.running, color)} "
        f"{_kv('skipped', checks.skipped, color)} "
        f"{_kv('unknown', checks.unknown, color)}"
    )


def _label(value: str, color: bool) -> str:
    return _style(value, color, _BOLD)


def _name(value: str, color: bool) -> str:
    return _style(value, color, _BOLD, _BLUE)


def _variable(value: str, color: bool) -> str:
    return _style(value, color, _VARIABLE)


def _muted(value: str, color: bool) -> str:
    return _style(value, color, _MUTED)


def _state(value: str, color: bool) -> str:
    if value in {
        "clean",
        "synced",
        "success",
        "open",
        "yes",
        "none",
        "0",
    }:
        return _style(value, color, _GREEN)
    if value in {
        "dirty",
        "ahead",
        "behind",
        "diverged",
        "pending",
        "running",
        "draft",
        "skipped",
        "mixed",
        "unknown",
    }:
        return _style(value, color, _AMBER)
    if value in {
        "conflicted",
        "failure",
        "closed",
        "unavailable",
        "timeout",
        "no",
    }:
        return _style(value, color, _RED)
    if value == "detached":
        return _style(value, color, _PURPLE)
    if value in {"no-upstream", "no_upstream", "not-requested"}:
        return _style(value, color, _COMMENT_GREEN)
    return value


def _kv(key: str, value: object, color: bool) -> str:
    return f"{key}={_number(str(value), color)}"


def _number(value: str, color: bool) -> str:
    return _style(value, color, _NUMBER)


def _style(value: str, color: bool, *codes: str) -> str:
    if not color or not codes:
        return value
    return f"{''.join(codes)}{value}{_RESET}"
