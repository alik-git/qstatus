"""Shared GitHub PR, check, run, and release evidence collection."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from quick_status.github_client import (
    GitHubClient,
    GitHubMemoryCache,
    JsonQueryResult,
)
from quick_status.models import (
    BranchState,
    CommandRecord,
    GitHubContext,
    PullRequestInfo,
    ReleaseInfo,
    RemoteCheckSummary,
    RepoSnapshot,
    RepoSummary,
)

if TYPE_CHECKING:
    from pathlib import Path

_PR_FIELDS = (
    "number,title,url,state,isDraft,baseRefName,baseRefOid,headRefName,"
    "headRefOid,reviewDecision,statusCheckRollup"
)
_RUN_FIELDS = (
    "databaseId,status,conclusion,headSha,headBranch,workflowName,"
    "displayTitle,event,createdAt,updatedAt,url,attempt"
)


@dataclass(frozen=True, slots=True)
class PullRequestQuery:
    """A branch PR plus its check rollup and source status."""

    status: str
    pull_request: PullRequestInfo | None
    check_rollup: list[dict[str, Any]]
    error: str | None = None


def enrich_repo_snapshot(
    snapshot: RepoSnapshot,
    github: GitHubContext,
    github_commands: list[CommandRecord],
) -> RepoSnapshot:
    """Attach shared GitHub evidence and its neutral summary to a repo snapshot."""
    return replace(
        snapshot,
        github=github,
        commands=[*snapshot.commands, *github_commands],
        summary=RepoSummary(
            sync_state=snapshot.summary.sync_state,
            worktree_state=snapshot.summary.worktree_state,
            pr_state=github.pr_state,
            remote_check_state=github.checks.state if github.checks else "unknown",
        ),
    )


def collect_github_context(
    *,
    repo: str | None,
    branch: BranchState,
    root: Path,
    include_commands: bool = False,
    include_release: bool = False,
    max_age_s: float = 0.0,
    timeout_s: float = 10.0,
    cache_dir: Path | None = None,
    memory_cache: GitHubMemoryCache | None = None,
) -> tuple[GitHubContext, list[CommandRecord]]:
    """Collect read-only GitHub facts through the shared bounded query plan."""
    if not repo:
        return (
            GitHubContext(
                status="unavailable",
                repo=None,
                pr_state="unknown",
                error="no GitHub remote detected",
            ),
            [],
        )

    client = GitHubClient(
        root,
        include_commands=include_commands,
        max_age_s=max_age_s,
        timeout_s=timeout_s,
        cache_dir=cache_dir,
        memory_cache=memory_cache,
    )
    pr_query = query_pull_request(client, repo=repo, branch=branch)
    if pr_query.status != "available":
        provenance = client.provenance()
        return (
            GitHubContext(
                status=pr_query.status,
                repo=repo,
                pr_state="unknown",
                error=pr_query.error,
                source=provenance.source,
                collected_at=provenance.collected_at,
                age_seconds=provenance.age_seconds,
            ),
            client.records,
        )

    pull_request = pr_query.pull_request
    error = None
    status = "available"
    if pull_request is not None and pull_request.state == "open":
        checks = summarize_status_rollup(
            pr_query.check_rollup,
            head_sha=pull_request.head_oid,
        )
    else:
        runs_query = query_workflow_runs(
            client,
            repo=repo,
            commit=branch.oid,
            branch=None,
        )
        if runs_query.ok:
            runs = runs_query.data if isinstance(runs_query.data, list) else []
            checks = summarize_workflow_runs(runs, head_sha=branch.oid)
        else:
            checks = RemoteCheckSummary(state="unknown", head_sha=branch.oid)
            status = _query_failure_status(runs_query)
            error = f"workflow-runs: {runs_query.error}"

    release = None
    if include_release:
        release, release_error = query_release(client, repo=repo, root=root)
        if release_error:
            status = "partial" if status == "available" else status
            error = _join_errors(error, release_error)

    provenance = client.provenance()
    return (
        GitHubContext(
            status=status,
            repo=repo,
            pr_state=_summarize_pr_state(pull_request),
            pull_request=pull_request,
            checks=checks,
            release=release,
            error=error,
            source=provenance.source,
            collected_at=provenance.collected_at,
            age_seconds=provenance.age_seconds,
        ),
        client.records,
    )


def query_pull_request(
    client: GitHubClient,
    *,
    repo: str,
    branch: BranchState,
) -> PullRequestQuery:
    """Query the current branch PR and check rollup in one GitHub call."""
    if branch.head in {"unknown", "(detached)"}:
        return PullRequestQuery(
            status="available",
            pull_request=None,
            check_rollup=[],
        )
    result = client.json_list(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch.head,
            "--state",
            "all",
            "--limit",
            "1",
            "--json",
            _PR_FIELDS,
        ],
    )
    if not result.ok:
        status = _query_failure_status(result)
        return PullRequestQuery(
            status=status,
            pull_request=None,
            check_rollup=[],
            error=(
                result.error
                if status == "unavailable"
                else f"pull-request: {result.error}"
            ),
        )
    items = result.data if isinstance(result.data, list) else []
    if not items:
        return PullRequestQuery(
            status="available",
            pull_request=None,
            check_rollup=[],
        )
    data = items[0]
    raw_rollup = data.get("statusCheckRollup")
    rollup = (
        [item for item in raw_rollup if isinstance(item, dict)]
        if isinstance(raw_rollup, list)
        else []
    )
    return PullRequestQuery(
        status="available",
        pull_request=_pull_request_from_mapping(data),
        check_rollup=rollup,
    )


def query_workflow_runs(
    client: GitHubClient,
    *,
    repo: str,
    commit: str | None,
    branch: str | None,
    limit: int = 20,
) -> JsonQueryResult:
    """Query workflow runs for one exact commit or branch."""
    args = [
        "run",
        "list",
        "--repo",
        repo,
        "--limit",
        str(limit),
        "--json",
        _RUN_FIELDS,
    ]
    if commit:
        args.extend(["--commit", commit])
    if branch:
        args.extend(["--branch", branch])
    return client.json_list(args)


def query_release(
    client: GitHubClient,
    *,
    repo: str,
    root: Path,
) -> tuple[ReleaseInfo | None, str | None]:
    """Query the project-version release only when explicitly requested."""
    version = _read_project_version(root)
    if not version:
        return None, None
    tag = f"v{version}"
    result = client.json_object(
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
        error = result.error or "unknown release query error"
        if _is_missing_release(error):
            return ReleaseInfo(version=version, tag=tag, exists=False), None
        return (
            ReleaseInfo(version=version, tag=tag, exists=None, error=error),
            f"release: {error}",
        )
    data = result.data if isinstance(result.data, dict) else {}
    return (
        ReleaseInfo(
            version=version,
            tag=_optional_str(data.get("tagName")) or tag,
            exists=True,
            url=_optional_str(data.get("url")),
        ),
        None,
    )


def summarize_status_rollup(
    checks: list[dict[str, Any]],
    *,
    head_sha: str | None,
) -> RemoteCheckSummary:
    """Summarize `statusCheckRollup` rows from a PR list query."""
    counts = _empty_counts()
    for item in checks:
        counts[status_rollup_bucket(item)] += 1
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


def _pull_request_from_mapping(data: dict[str, Any]) -> PullRequestInfo:
    return PullRequestInfo(
        number=int(data.get("number", 0)),
        title=str(data.get("title") or ""),
        url=str(data.get("url") or ""),
        state=str(data.get("state") or "UNKNOWN").lower(),
        is_draft=bool(data.get("isDraft")),
        base_ref=_optional_str(data.get("baseRefName")),
        head_ref=_optional_str(data.get("headRefName")),
        review_decision=_optional_str(data.get("reviewDecision")),
        base_oid=_optional_str(data.get("baseRefOid")),
        head_oid=_optional_str(data.get("headRefOid")),
    )


def status_rollup_bucket(item: dict[str, Any]) -> str:
    """Normalize one PR status-rollup row to a summary bucket."""
    status = str(item.get("status") or "").lower()
    conclusion = str(item.get("conclusion") or item.get("state") or "").lower()
    if status in {"in_progress"}:
        return "running"
    if status in {"queued", "pending", "requested", "waiting"}:
        return "pending"
    if conclusion in {"success", "neutral"}:
        return "success" if conclusion == "success" else "skipped"
    if conclusion in {
        "failure",
        "error",
        "timed_out",
        "cancelled",
        "startup_failure",
        "action_required",
    }:
        return "failure"
    if conclusion in {"pending", "expected"}:
        return "pending"
    if conclusion == "skipped":
        return "skipped"
    return "unknown"


def _summary_from_counts(
    counts: dict[str, int],
    *,
    head_sha: str | None,
) -> RemoteCheckSummary:
    return RemoteCheckSummary(
        state=_remote_check_state(counts),
        total=sum(counts.values()),
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


def _query_failure_status(result: JsonQueryResult) -> str:
    if result.command.unavailable:
        return "unavailable"
    error = (result.error or "").lower()
    if "auth" in error or "login" in error or "not logged" in error:
        return "unavailable"
    return "error"


def _summarize_pr_state(pull_request: PullRequestInfo | None) -> str:
    if pull_request is None:
        return "none"
    if pull_request.is_draft:
        return "draft"
    state = pull_request.state.lower()
    return state if state in {"open", "closed", "merged"} else "unknown"


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


def _is_missing_release(error: str) -> bool:
    normalized = error.lower()
    return "release not found" in normalized or "no release found" in normalized


def _join_errors(left: str | None, right: str) -> str:
    return f"{left}; {right}" if left else right


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
