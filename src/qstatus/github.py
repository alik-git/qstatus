"""Optional GitHub context collection through the `gh` CLI."""

from __future__ import annotations

import json
import tomllib
from typing import TYPE_CHECKING, Any

from qstatus.commands import CommandResult, run_command
from qstatus.models import (
    BranchState,
    CommandRecord,
    GitHubContext,
    PullRequestInfo,
    ReleaseInfo,
    RemoteCheckSummary,
)

if TYPE_CHECKING:
    from pathlib import Path


def collect_github_context(
    *,
    repo: str | None,
    branch: BranchState,
    root: Path,
    include_commands: bool = False,
) -> tuple[GitHubContext, list[CommandRecord]]:
    """Collect read-only GitHub PR, check, and release facts."""
    command_records: list[CommandRecord] = []
    if not repo:
        return (
            GitHubContext(
                status="unavailable",
                repo=None,
                pr_state="unknown",
                error="no GitHub remote detected",
            ),
            command_records,
        )

    def gh(args: list[str], *, timeout_s: float = 8.0) -> CommandResult:
        result = run_command(["gh", *args], cwd=root, timeout_s=timeout_s)
        if include_commands:
            command_records.append(result.evidence())
        return result

    auth_result = gh(["auth", "status"], timeout_s=5.0)
    if auth_result.unavailable:
        return (
            GitHubContext(
                status="unavailable",
                repo=repo,
                pr_state="unknown",
                error="gh is not installed",
            ),
            command_records,
        )
    if not auth_result.ok:
        detail = auth_result.stderr.strip() or auth_result.stdout.strip()
        return (
            GitHubContext(
                status="unavailable",
                repo=repo,
                pr_state="unknown",
                error=f"gh auth unavailable: {detail}",
            ),
            command_records,
        )

    pull_request = _collect_pull_request(gh, repo, branch)
    checks = _collect_checks(gh, repo, branch, pull_request)
    release = _collect_release(gh, repo, root)
    pr_state = _summarize_pr_state(pull_request)
    return (
        GitHubContext(
            status="available",
            repo=repo,
            pr_state=pr_state,
            pull_request=pull_request,
            checks=checks,
            release=release,
        ),
        command_records,
    )


def _collect_pull_request(
    gh,
    repo: str,
    branch: BranchState,
) -> PullRequestInfo | None:
    if branch.head in {"unknown", "(detached)"}:
        return None
    result = gh(
        [
            "pr",
            "view",
            branch.head,
            "--repo",
            repo,
            "--json",
            "number,title,url,state,isDraft,baseRefName,headRefName,reviewDecision",
        ],
    )
    if not result.ok:
        return _collect_pull_request_from_list(gh, repo, branch.head)
    data = _loads_object(result.stdout)
    if data is None:
        return _collect_pull_request_from_list(gh, repo, branch.head)
    return PullRequestInfo(
        number=int(data.get("number", 0)),
        title=str(data.get("title") or ""),
        url=str(data.get("url") or ""),
        state=str(data.get("state") or "UNKNOWN").lower(),
        is_draft=bool(data.get("isDraft")),
        base_ref=_optional_str(data.get("baseRefName")),
        head_ref=_optional_str(data.get("headRefName")),
        review_decision=_optional_str(data.get("reviewDecision")),
    )


def _collect_pull_request_from_list(
    gh,
    repo: str,
    branch_name: str,
) -> PullRequestInfo | None:
    result = gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch_name,
            "--state",
            "all",
            "--limit",
            "1",
            "--json",
            "number,title,url,state,isDraft,baseRefName,headRefName,reviewDecision",
        ],
    )
    if not result.ok:
        return None
    items = _loads_list(result.stdout)
    if not items:
        return None
    data = items[0]
    return PullRequestInfo(
        number=int(data.get("number", 0)),
        title=str(data.get("title") or ""),
        url=str(data.get("url") or ""),
        state=str(data.get("state") or "UNKNOWN").lower(),
        is_draft=bool(data.get("isDraft")),
        base_ref=_optional_str(data.get("baseRefName")),
        head_ref=_optional_str(data.get("headRefName")),
        review_decision=_optional_str(data.get("reviewDecision")),
    )


def _collect_checks(
    gh,
    repo: str,
    branch: BranchState,
    pull_request: PullRequestInfo | None,
) -> RemoteCheckSummary:
    if pull_request is not None:
        result = gh(
            [
                "pr",
                "checks",
                str(pull_request.number),
                "--repo",
                repo,
                "--json",
                "name,state,bucket,workflow,link",
            ],
        )
        if result.ok:
            items = _loads_list(result.stdout)
            if items is not None:
                return summarize_pr_checks(items, head_sha=branch.oid)

    args = [
        "run",
        "list",
        "--repo",
        repo,
        "--limit",
        "20",
        "--json",
        "status,conclusion,headSha,headBranch,workflowName,displayTitle,url",
    ]
    if branch.head not in {"unknown", "(detached)"}:
        args.extend(["--branch", branch.head])
    if branch.oid:
        args.extend(["--commit", branch.oid])
    result = gh(args)
    if not result.ok:
        return RemoteCheckSummary(state="unknown", head_sha=branch.oid)
    runs = _loads_list(result.stdout)
    if runs is None:
        return RemoteCheckSummary(state="unknown", head_sha=branch.oid)
    return summarize_workflow_runs(runs, head_sha=branch.oid)


def _collect_release(gh, repo: str, root: Path) -> ReleaseInfo | None:
    version = _read_project_version(root)
    if not version:
        return None
    tag = f"v{version}"
    result = gh(
        [
            "release",
            "view",
            tag,
            "--repo",
            repo,
            "--json",
            "tagName,url,targetCommitish,isDraft,isPrerelease",
        ],
    )
    if not result.ok:
        return ReleaseInfo(version=version, tag=tag, exists=False)
    data = _loads_object(result.stdout)
    if data is None:
        return ReleaseInfo(version=version, tag=tag, exists=None)
    return ReleaseInfo(
        version=version,
        tag=_optional_str(data.get("tagName")) or tag,
        exists=True,
        url=_optional_str(data.get("url")),
    )


def summarize_pr_checks(
    checks: list[dict[str, Any]],
    *,
    head_sha: str | None,
) -> RemoteCheckSummary:
    """Summarize `gh pr checks --json` rows."""
    counts = _empty_counts()
    for item in checks:
        bucket = str(item.get("bucket") or "").lower()
        if bucket == "pass":
            counts["success"] += 1
        elif bucket in {"fail", "cancel"}:
            counts["failure"] += 1
        elif bucket == "pending":
            counts["pending"] += 1
        elif bucket == "skipping":
            counts["skipped"] += 1
        else:
            counts["unknown"] += 1
    return _summary_from_counts(counts, head_sha=head_sha)


def summarize_workflow_runs(
    runs: list[dict[str, Any]],
    *,
    head_sha: str | None,
) -> RemoteCheckSummary:
    """Summarize `gh run list --json` rows."""
    counts = _empty_counts()
    for item in runs:
        status = str(item.get("status") or "").lower()
        conclusion = str(item.get("conclusion") or "").lower()
        if status == "completed":
            if conclusion == "success":
                counts["success"] += 1
            elif conclusion in {"failure", "timed_out", "cancelled", "startup_failure"}:
                counts["failure"] += 1
            elif conclusion in {"skipped", "neutral"}:
                counts["skipped"] += 1
            else:
                counts["unknown"] += 1
        elif status == "in_progress":
            counts["running"] += 1
        elif status in {"queued", "pending", "requested", "waiting"}:
            counts["pending"] += 1
        else:
            counts["unknown"] += 1
    return _summary_from_counts(counts, head_sha=head_sha)


def _summary_from_counts(
    counts: dict[str, int],
    *,
    head_sha: str | None,
) -> RemoteCheckSummary:
    total = sum(counts.values())
    state = _remote_check_state(counts)
    return RemoteCheckSummary(
        state=state,
        total=total,
        success=counts["success"],
        failure=counts["failure"],
        pending=counts["pending"],
        running=counts["running"],
        skipped=counts["skipped"],
        unknown=counts["unknown"],
        head_sha=head_sha,
    )


def _remote_check_state(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return "none"
    active_categories = sum(1 for value in counts.values() if value)
    if counts["failure"] and active_categories > 1:
        return "mixed"
    if counts["failure"]:
        return "failure"
    if counts["running"]:
        return "running"
    if counts["pending"]:
        return "pending"
    if counts["unknown"] and active_categories > 1:
        return "mixed"
    if counts["unknown"]:
        return "unknown"
    if counts["success"] and counts["skipped"]:
        return "mixed"
    if counts["success"]:
        return "success"
    if counts["skipped"]:
        return "skipped"
    return "unknown"


def _summarize_pr_state(pull_request: PullRequestInfo | None) -> str:
    if pull_request is None:
        return "none"
    if pull_request.is_draft:
        return "draft"
    state = pull_request.state.lower()
    if state in {"open", "closed", "merged"}:
        return state
    return "unknown"


def _read_project_version(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        data = tomllib.loads(pyproject.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


def _loads_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _loads_list(text: str) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, dict)]


def _empty_counts() -> dict[str, int]:
    return {
        "success": 0,
        "failure": 0,
        "pending": 0,
        "running": 0,
        "skipped": 0,
        "unknown": 0,
    }


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
