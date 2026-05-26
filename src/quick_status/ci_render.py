"""Human and JSON renderers for quick_status CI snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quick_status import formatting as fmt

if TYPE_CHECKING:
    from quick_status.ci_models import CiJob, CiRun, CiSnapshot


def render_ci_json(snapshot: CiSnapshot, *, verbose: bool = False) -> str:
    """Render a CI snapshot as stable JSON."""
    return json.dumps(
        snapshot.to_dict(include_commands=verbose),
        indent=2,
        sort_keys=True,
    )


def render_ci_human(
    snapshot: CiSnapshot,
    *,
    verbose: bool = False,
    color: bool = False,
) -> str:
    """Render a human-readable CI snapshot."""
    lines = [
        _ci_line(snapshot, color=color),
        _branch_line(snapshot, color=color),
        _state_line(snapshot, color=color),
        _pr_line(snapshot, color=color),
        _current_line(snapshot, color=color),
        _summary_line(snapshot, color=color),
        *_run_lines(snapshot.runs, color=color),
        *_job_lines(snapshot.jobs, color=color),
        *_log_tail_lines(snapshot, color=color),
    ]
    if snapshot.github.status != "available" and snapshot.github.error:
        lines.append(
            f"{fmt.label('GITHUB', color)} "
            f"{fmt.state(snapshot.github.status, color)} "
            f"reason={snapshot.github.error}"
        )
    if snapshot.source_errors:
        lines.extend(
            f"{fmt.label('SOURCE_ERROR', color)} {error}"
            for error in snapshot.source_errors
        )
    if verbose:
        lines.extend(fmt.command_lines(snapshot.commands, color=color))
    return "\n".join(lines)


def _ci_line(snapshot: CiSnapshot, *, color: bool) -> str:
    repo_name = fmt.name(snapshot.repo.name, color)
    github_repo = snapshot.github.repo or snapshot.repo.github_repo or "-"
    return f"{fmt.label('CI', color)} {repo_name} {github_repo}"


def _branch_line(snapshot: CiSnapshot, *, color: bool) -> str:
    branch = snapshot.branch
    upstream = branch.upstream or "no-upstream"
    local = _short(snapshot.commits.local_head) or "-"
    parts = [
        f"{fmt.label('BRANCH', color)} {fmt.name(branch.head, color)}",
        f"local={fmt.muted(local, color)}",
        f"upstream={fmt.muted(upstream, color)}",
        fmt.state(branch.sync_state, color),
    ]
    return " ".join(parts)


def _state_line(snapshot: CiSnapshot, *, color: bool) -> str:
    changes = snapshot.changes
    return (
        f"{fmt.label('STATE', color)} {fmt.state(changes.worktree_state, color)} "
        f"{fmt.kv('staged', changes.staged, color)} "
        f"{fmt.kv('unstaged', changes.unstaged, color)} "
        f"{fmt.kv('untracked', changes.untracked, color)} "
        f"{fmt.kv('conflicts', changes.conflicted, color)}"
    )


def _pr_line(snapshot: CiSnapshot, *, color: bool) -> str:
    pull_request = snapshot.pull_request
    if pull_request is None:
        return f"{fmt.label('PR', color)} none"
    head = _short(pull_request.head_oid) or "-"
    base = pull_request.base_ref or "-"
    return (
        f"{fmt.label('PR', color)} #{pull_request.number} "
        f"{fmt.state(pull_request.state, color)} "
        f"head={fmt.muted(head, color)} base={base} url={pull_request.url}"
    )


def _current_line(snapshot: CiSnapshot, *, color: bool) -> str:
    currentness = snapshot.currentness
    expected = _short(currentness.expected_oid) or "-"
    checked = _short(currentness.checked_oid) or "-"
    return (
        f"{fmt.label('CURRENT', color)} {fmt.state(currentness.state, color)} "
        f"expected={fmt.muted(expected, color)} checked={fmt.muted(checked, color)} "
        f"source={currentness.source} reason={currentness.reason}"
    )


def _summary_line(snapshot: CiSnapshot, *, color: bool) -> str:
    summary = snapshot.summary
    if summary is None:
        return f"{fmt.label('CHECKS', color)} {fmt.state('unknown', color)}"
    label = "CHECKS" if snapshot.checks else "RUNS"
    return (
        f"{fmt.label(label, color)} {fmt.state(summary.ci_state, color)} "
        f"{fmt.kv('total', summary.total_checks, color)} "
        f"{fmt.kv('pass', summary.pass_count, color)} "
        f"{fmt.kv('fail', summary.fail_count, color)} "
        f"{fmt.kv('pending', summary.pending_count, color)} "
        f"{fmt.kv('running', summary.running_count, color)} "
        f"{fmt.kv('skipped', summary.skipped_count, color)} "
        f"{fmt.kv('cancel', summary.cancel_count, color)} "
        f"{fmt.kv('unknown', summary.unknown_count, color)} "
        f"applies_to_head={fmt.state(_applies_to_head(summary.currentness), color)}"
    )


def _run_lines(runs: list[CiRun], *, color: bool) -> list[str]:
    selected = runs[:5]
    lines: list[str] = []
    for run in selected:
        name = run.workflow_name or run.display_title or "run"
        run_id = run.database_id if run.database_id is not None else "-"
        sha = _short(run.head_sha) or "-"
        url = run.url or "-"
        lines.append(
            f"{fmt.label('RUN', color)} {name} "
            f"{fmt.state(_display_bucket(run.bucket), color)} "
            f"id={run_id} sha={fmt.muted(sha, color)} currentness={run.currentness} "
            f"url={url}"
        )
    return lines


def _job_lines(jobs: list[CiJob], *, color: bool) -> list[str]:
    return [
        (
            f"{fmt.label('JOB', color)} {job.name} "
            f"{fmt.state(_display_bucket(job.bucket), color)} "
            f"url={job.url or '-'}"
        )
        for job in jobs
    ]


def _log_tail_lines(snapshot: CiSnapshot, *, color: bool) -> list[str]:
    lines: list[str] = []
    for tail in snapshot.log_tails:
        if tail.status != "available":
            reason = tail.reason or "unknown"
            lines.append(
                f"{fmt.label('LOG', color)} unavailable "
                f"run={tail.run_database_id or '-'} reason={reason}"
            )
            continue
        lines.append(
            f"{fmt.label('LOG', color)} tail "
            f"run={tail.run_database_id or '-'} "
            f"lines={len(tail.lines)} capped={'yes' if tail.capped else 'no'}"
        )
        lines.extend(f"  {line}" for line in tail.lines)
    return lines


def _short(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:7]


def _display_bucket(bucket: str) -> str:
    return {
        "pass": "success",
        "fail": "failure",
        "cancel": "cancelled",
        "skipping": "skipped",
    }.get(bucket, bucket)


def _applies_to_head(currentness: str) -> str:
    if currentness == "current":
        return "yes"
    if currentness == "stale":
        return "no"
    return "unknown"
