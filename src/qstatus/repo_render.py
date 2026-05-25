"""Human and JSON renderers for qstatus repository snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from qstatus import formatting as fmt

if TYPE_CHECKING:
    from qstatus.models import (
        RemoteInfo,
        RepoSnapshot,
        StashEntry,
        SubmoduleSummary,
        WorktreeEntry,
    )


def render_repo_json(snapshot: RepoSnapshot, *, verbose: bool = False) -> str:
    """Render a repo snapshot as stable JSON."""
    return json.dumps(
        snapshot.to_dict(include_commands=verbose),
        indent=2,
        sort_keys=True,
    )


def render_repo_human(
    snapshot: RepoSnapshot,
    *,
    verbose: bool = False,
    color: bool = False,
    compact: bool = True,
    show_worktrees: bool = False,
    show_stashes: bool = False,
) -> str:
    """Render a human-readable repo snapshot."""
    lines = [
        *render_repo_local_lines(
            snapshot,
            color=color,
            compact=compact,
            show_worktrees=show_worktrees,
            show_stashes=show_stashes,
        ),
        *render_repo_github_lines(snapshot, color=color, compact=compact),
    ]
    if verbose:
        lines.extend(
            render_repo_verbose_lines(snapshot, color=color, compact=compact),
        )
    return "\n".join(lines)


def render_repo_local_lines(
    snapshot: RepoSnapshot,
    *,
    color: bool = False,
    compact: bool = True,
    show_worktrees: bool = False,
    show_stashes: bool = False,
) -> list[str]:
    """Render local Git facts that are available before optional GitHub calls."""
    if compact:
        return _render_repo_local_compact_lines(
            snapshot,
            color=color,
            show_worktrees=show_worktrees,
            show_stashes=show_stashes,
        )

    branch = snapshot.branch
    changes = snapshot.changes
    remote = _origin_or_first_remote(snapshot)
    commit = branch.short_oid or "no-commit"
    stash = changes.stash_count if changes.stash_count is not None else "unknown"

    lines = [
        *fmt.hybrid_section(
            "REPO",
            path_rows=[("root", fmt.variable(snapshot.repo.root, color))],
            scalar_rows=[("name", fmt.name(snapshot.repo.name, color))],
            color=color,
        ),
        *fmt.hybrid_section(
            "BRANCH",
            path_rows=[],
            scalar_rows=[
                ("head", fmt.name(branch.head, color)),
                ("commit", fmt.muted(commit, color)),
                ("upstream", fmt.state(branch.upstream or "no-upstream", color)),
                ("sync", fmt.state(branch.sync_state, color)),
                ("ahead", fmt.number(str(branch.ahead), color)),
                ("behind", fmt.number(str(branch.behind), color)),
            ],
            color=color,
        ),
        *fmt.hybrid_section(
            "STATE",
            path_rows=[],
            scalar_rows=[
                ("worktree", fmt.state(changes.worktree_state, color)),
                ("staged", fmt.number(str(changes.staged), color)),
                ("unstaged", fmt.number(str(changes.unstaged), color)),
                ("untracked", fmt.number(str(changes.untracked), color)),
                ("conflicts", fmt.number(str(changes.conflicted), color)),
                ("stash", fmt.number(str(stash), color)),
            ],
            color=color,
        ),
        *_repo_remote_section(remote, color=color),
        *_repo_submodules_section(snapshot.submodules, color=color),
    ]
    if show_worktrees:
        lines.extend(_repo_worktree_lines(snapshot, color=color))
    if show_stashes:
        lines.extend(_repo_stash_lines(snapshot, color=color))
    return lines


def render_repo_github_lines(
    snapshot: RepoSnapshot,
    *,
    color: bool = False,
    compact: bool = True,
) -> list[str]:
    """Render optional GitHub facts after GitHub context is available."""
    if compact:
        return _render_repo_github_compact_lines(snapshot, color=color)

    github = snapshot.github
    lines = [
        *_repo_pr_section(snapshot, color=color),
        *_repo_ci_section(snapshot, color=color),
    ]
    if github.release is not None:
        release = github.release
        exists = (
            "yes" if release.exists else "no" if release.exists is False else "unknown"
        )
        lines.extend(
            fmt.hybrid_section(
                "RELEASE",
                path_rows=[],
                scalar_rows=[
                    (
                        "tag",
                        fmt.name(release.tag or release.version or "unknown", color),
                    ),
                    ("exists", fmt.state(exists, color)),
                ],
                color=color,
            ),
        )
    return lines


def render_repo_verbose_lines(
    snapshot: RepoSnapshot,
    *,
    color: bool = False,
    compact: bool = True,
) -> list[str]:
    """Render extra debug evidence after the main local/GitHub summary."""
    if compact:
        return _render_repo_verbose_compact_lines(snapshot, color=color)

    branch = snapshot.branch
    changes = snapshot.changes
    lines: list[str] = []
    if branch.commit_subject:
        lines.extend(fmt.notice_lines("COMMIT", branch.commit_subject, color=color))
    lines.extend(
        fmt.hybrid_section(
            "WORKTREES",
            path_rows=[],
            scalar_rows=[("count", fmt.number(str(snapshot.worktree.count), color))],
            color=color,
        ),
    )
    if changes.diff_shortstat:
        lines.extend(fmt.notice_lines("DIFF", changes.diff_shortstat, color=color))
    if changes.cached_diff_shortstat:
        lines.extend(
            fmt.notice_lines(
                "CACHED_DIFF",
                changes.cached_diff_shortstat,
                color=color,
            ),
        )
    if snapshot.github.error:
        lines.extend(
            fmt.notice_lines("GITHUB_ERROR", snapshot.github.error, color=color)
        )
    lines.extend(fmt.command_lines(snapshot.commands, color=color))
    return lines


def _render_repo_local_compact_lines(
    snapshot: RepoSnapshot,
    *,
    color: bool = False,
    show_worktrees: bool = False,
    show_stashes: bool = False,
) -> list[str]:
    branch = snapshot.branch
    changes = snapshot.changes
    remote = _origin_or_first_remote(snapshot)
    upstream = branch.upstream or "no-upstream"
    commit = branch.short_oid or "no-commit"
    stash = changes.stash_count if changes.stash_count is not None else "unknown"

    lines = [
        (
            f"{fmt.label('REPO', color)} {fmt.name(snapshot.repo.name, color)} "
            f"{fmt.variable(snapshot.repo.root, color)}"
        ),
        (
            f"{fmt.label('BRANCH', color)} {fmt.name(branch.head, color)} "
            f"{fmt.muted(commit, color)} {fmt.muted(upstream, color)} "
            f"{fmt.state(branch.sync_state, color)} "
            f"{fmt.kv('ahead', branch.ahead, color)} "
            f"{fmt.kv('behind', branch.behind, color)}"
        ),
        (
            f"{fmt.label('STATE', color)} {fmt.state(changes.worktree_state, color)} "
            f"{fmt.kv('staged', changes.staged, color)} "
            f"{fmt.kv('unstaged', changes.unstaged, color)} "
            f"{fmt.kv('untracked', changes.untracked, color)} "
            f"{fmt.kv('conflicts', changes.conflicted, color)} "
            f"{fmt.kv('stash', stash, color)}"
        ),
        f"{fmt.label('REMOTE', color)} {_format_remote(remote, color=color)}",
        (
            f"{fmt.label('SUBMODULES', color)} "
            f"{_format_submodules(snapshot.submodules, color=color)}"
        ),
    ]
    if show_worktrees:
        lines.extend(_repo_worktree_lines(snapshot, color=color))
    if show_stashes:
        lines.extend(_repo_stash_lines(snapshot, color=color))
    return lines


def _render_repo_github_compact_lines(
    snapshot: RepoSnapshot, *, color: bool = False
) -> list[str]:
    github = snapshot.github
    lines = [
        f"{fmt.label('PR', color)} {_format_pr(snapshot, color=color)}",
        f"{fmt.label('CI', color)} {_format_ci(snapshot, color=color)}",
    ]
    if github.release is not None:
        release = github.release
        exists = (
            "yes" if release.exists else "no" if release.exists is False else "unknown"
        )
        release_name = release.tag or release.version or "unknown"
        lines.append(
            f"{fmt.label('RELEASE', color)} {fmt.name(release_name, color)} "
            f"exists={fmt.state(exists, color)}",
        )
    return lines


def _render_repo_verbose_compact_lines(
    snapshot: RepoSnapshot, *, color: bool = False
) -> list[str]:
    branch = snapshot.branch
    changes = snapshot.changes
    lines: list[str] = []
    if branch.commit_subject:
        lines.append(f"{fmt.label('COMMIT', color)} {branch.commit_subject}")
    lines.append(
        f"{fmt.label('WORKTREES', color)} "
        f"{fmt.kv('count', snapshot.worktree.count, color)}",
    )
    if changes.diff_shortstat:
        lines.append(f"{fmt.label('DIFF', color)} {changes.diff_shortstat}")
    if changes.cached_diff_shortstat:
        lines.append(
            f"{fmt.label('CACHED_DIFF', color)} {changes.cached_diff_shortstat}",
        )
    if snapshot.github.error:
        lines.append(f"{fmt.label('GITHUB_ERROR', color)} {snapshot.github.error}")
    for command in snapshot.commands:
        status = fmt.command_status(command)
        lines.append(
            f"{fmt.label('CMD', color)} {fmt.state(str(status), color)} "
            f"{' '.join(command.args)}",
        )
    return lines


def _repo_worktree_lines(snapshot: RepoSnapshot, *, color: bool) -> list[str]:
    worktree = snapshot.worktree
    current = fmt.path(worktree.current_path, color, abs_paths=False)
    lines = [
        (
            f"{fmt.label('WORKTREES', color)} "
            f"{fmt.kv('count', worktree.count, color)} current={current}"
        ),
    ]
    if not worktree.worktrees:
        return lines

    path_values = [fmt.compact_home(entry.path) for entry in worktree.worktrees]
    branch_values = [_worktree_branch_label(entry) for entry in worktree.worktrees]
    path_width = max(len(path) for path in path_values)
    branch_width = max(len(branch) for branch in branch_values)

    for entry, path_value, branch_value in zip(
        worktree.worktrees,
        path_values,
        branch_values,
        strict=True,
    ):
        flags = _worktree_flags(entry)
        flag_text = " ".join(fmt.state(flag, color) for flag in flags)
        head = (entry.head or "")[:7] or "-"
        padding_after_path = " " * (path_width - len(path_value) + 2)
        padding_after_branch = " " * (branch_width - len(branch_value) + 2)
        line = (
            f"  {fmt.variable(path_value, color)}{padding_after_path}"
            f"{fmt.name(branch_value, color)}{padding_after_branch}"
            f"{fmt.muted(head, color)}"
        )
        if flag_text:
            line = f"{line} {flag_text}"
        lines.append(line)
    return lines


def _repo_stash_lines(snapshot: RepoSnapshot, *, color: bool) -> list[str]:
    stashes = snapshot.stashes
    count = stashes.count if stashes.count is not None else "unknown"
    lines = [
        (
            f"{fmt.label('STASHES', color)} "
            f"{fmt.kv('count', count, color)} "
            f"detail={fmt.state(stashes.detail_status, color)}"
        ),
    ]
    lines.extend(
        f"  {_format_stash_entry(entry, color=color)}" for entry in stashes.entries
    )
    return lines


def _repo_remote_section(remote: RemoteInfo | None, *, color: bool) -> list[str]:
    if remote is None:
        return fmt.hybrid_section(
            "REMOTE",
            path_rows=[],
            scalar_rows=[("state", fmt.state("none", color))],
            color=color,
        )
    return [
        fmt.label("REMOTE", color),
        f"  {fmt.name(remote.name, color)}  {_remote_url(remote, color=color)}",
    ]


def _repo_submodules_section(submodules: SubmoduleSummary, *, color: bool) -> list[str]:
    if not submodules.present:
        return fmt.hybrid_section(
            "SUBMODULES",
            path_rows=[],
            scalar_rows=[("state", fmt.state("none", color))],
            color=color,
        )
    return fmt.hybrid_section(
        "SUBMODULES",
        path_rows=[],
        scalar_rows=[
            ("state", fmt.state(_submodule_state(submodules), color)),
            ("total", fmt.number(str(submodules.total), color)),
            ("clean", fmt.number(str(submodules.clean), color)),
            ("changed", fmt.number(str(submodules.changed), color)),
            ("uninitialized", fmt.number(str(submodules.uninitialized), color)),
            ("conflicts", fmt.number(str(submodules.conflicted), color)),
            ("unknown", fmt.number(str(submodules.unknown), color)),
        ],
        color=color,
    )


def _repo_pr_section(snapshot: RepoSnapshot, *, color: bool) -> list[str]:
    github = snapshot.github
    if github.status == "not_requested":
        return fmt.hybrid_section(
            "PR",
            path_rows=[],
            scalar_rows=[("state", fmt.state("not-requested", color))],
            color=color,
        )
    if github.status == "unavailable":
        lines = fmt.hybrid_section(
            "PR",
            path_rows=[],
            scalar_rows=[("state", fmt.state("unavailable", color))],
            color=color,
        )
        if github.error:
            lines.append(
                f"  {fmt.muted('error', color)}  {fmt.variable(github.error, color)}",
            )
        return lines
    if github.pull_request is None:
        return fmt.hybrid_section(
            "PR",
            path_rows=[],
            scalar_rows=[("state", fmt.state("none", color))],
            color=color,
        )
    pull = github.pull_request
    return fmt.hybrid_section(
        "PR",
        path_rows=[("url", fmt.variable(pull.url, color))],
        scalar_rows=[
            ("number", fmt.name(f"#{pull.number}", color)),
            ("state", fmt.state(pull.state, color)),
            ("draft", fmt.state(fmt.yes_no(pull.is_draft), color)),
            ("base", fmt.optional_value(pull.base_ref, color)),
            ("head", fmt.optional_value(pull.head_ref, color)),
            ("review", fmt.optional_value(pull.review_decision, color)),
        ],
        color=color,
    )


def _repo_ci_section(snapshot: RepoSnapshot, *, color: bool) -> list[str]:
    github = snapshot.github
    if github.status == "not_requested":
        return fmt.hybrid_section(
            "CI",
            path_rows=[],
            scalar_rows=[("state", fmt.state("not-requested", color))],
            color=color,
        )
    if github.status == "unavailable" or github.checks is None:
        return fmt.hybrid_section(
            "CI",
            path_rows=[],
            scalar_rows=[("state", fmt.state("unknown", color))],
            color=color,
        )
    checks = github.checks
    return fmt.hybrid_section(
        "CI",
        path_rows=[],
        scalar_rows=[
            ("state", fmt.state(checks.state, color)),
            ("total", fmt.number(str(checks.total), color)),
            ("success", fmt.number(str(checks.success), color)),
            ("failure", fmt.number(str(checks.failure), color)),
            ("pending", fmt.number(str(checks.pending), color)),
            ("running", fmt.number(str(checks.running), color)),
            ("skipped", fmt.number(str(checks.skipped), color)),
            ("unknown", fmt.number(str(checks.unknown), color)),
        ],
        color=color,
    )


def _origin_or_first_remote(snapshot: RepoSnapshot) -> RemoteInfo | None:
    for remote in snapshot.repo.remotes:
        if remote.name == "origin":
            return remote
    return snapshot.repo.remotes[0] if snapshot.repo.remotes else None


def _format_remote(remote: RemoteInfo | None, *, color: bool) -> str:
    if remote is None:
        return fmt.state("none", color)
    return f"{fmt.name(remote.name, color)} {_remote_url(remote, color=color)}"


def _format_submodules(submodules: SubmoduleSummary, *, color: bool) -> str:
    if not submodules.present:
        return fmt.state("none", color)
    return (
        f"{fmt.state(_submodule_state(submodules), color)} "
        f"{fmt.kv('total', submodules.total, color)} "
        f"{fmt.kv('clean', submodules.clean, color)} "
        f"{fmt.kv('changed', submodules.changed, color)} "
        f"{fmt.kv('uninitialized', submodules.uninitialized, color)} "
        f"{fmt.kv('conflicts', submodules.conflicted, color)} "
        f"{fmt.kv('unknown', submodules.unknown, color)}"
    )


def _format_pr(snapshot: RepoSnapshot, *, color: bool) -> str:
    github = snapshot.github
    if github.status == "not_requested":
        return fmt.state("not-requested", color)
    if github.status == "unavailable":
        return f"{fmt.state('unavailable', color)} {github.error or ''}".strip()
    if github.pull_request is None:
        return fmt.state("none", color)
    pr = github.pull_request
    draft = " draft" if pr.is_draft else ""
    return (
        f"{fmt.name(f'#{pr.number}{draft}', color)} {fmt.state(pr.state, color)} "
        f"{fmt.variable(pr.url, color)}"
    )


def _format_ci(snapshot: RepoSnapshot, *, color: bool) -> str:
    github = snapshot.github
    if github.status == "not_requested":
        return fmt.state("not-requested", color)
    if github.status == "unavailable":
        return fmt.state("unknown", color)
    checks = github.checks
    if checks is None:
        return fmt.state("unknown", color)
    return (
        f"{fmt.state(checks.state, color)} {fmt.kv('total', checks.total, color)} "
        f"{fmt.kv('success', checks.success, color)} "
        f"{fmt.kv('failure', checks.failure, color)} "
        f"{fmt.kv('pending', checks.pending, color)} "
        f"{fmt.kv('running', checks.running, color)} "
        f"{fmt.kv('skipped', checks.skipped, color)} "
        f"{fmt.kv('unknown', checks.unknown, color)}"
    )


def _submodule_state(submodules: SubmoduleSummary) -> str:
    if (
        submodules.changed == 0
        and submodules.uninitialized == 0
        and submodules.conflicted == 0
        and submodules.unknown == 0
    ):
        return "clean"
    return "dirty"


def _remote_url(remote: RemoteInfo, *, color: bool) -> str:
    return fmt.variable(remote.fetch_url or remote.push_url or "unknown-url", color)


def _worktree_branch_label(entry: WorktreeEntry) -> str:
    if entry.branch:
        return entry.branch
    if entry.detached:
        return "detached"
    if entry.bare:
        return "bare"
    return "unknown"


def _worktree_flags(entry: WorktreeEntry) -> list[str]:
    flags: list[str] = []
    if entry.is_current:
        flags.append("current")
    if entry.prunable:
        flags.append("prunable")
    if entry.detached:
        flags.append("detached")
    if entry.bare:
        flags.append("bare")
    return flags


def _format_stash_entry(entry: StashEntry, *, color: bool) -> str:
    files = entry.file_count if entry.file_count is not None else "unknown"
    parts = [
        fmt.name(entry.ref, color),
        f"branch={fmt.optional_value(entry.branch, color)}",
        f"files={fmt.number(str(files), color)}",
    ]
    if entry.detail_status != "available":
        parts.append(f"detail={fmt.state(entry.detail_status, color)}")
    subject = entry.subject.replace('"', '\\"')
    parts.append(f'subject="{fmt.variable(subject, color)}"')
    return " ".join(parts)
