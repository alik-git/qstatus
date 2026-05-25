"""Collect qstatus CI snapshots through the GitHub CLI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from qstatus.ci_models import (
    CI_SCHEMA_VERSION,
    CiCheck,
    CiCommitRefs,
    CiCurrentness,
    CiGitHubStatus,
    CiJob,
    CiLogTail,
    CiPullRequest,
    CiRun,
    CiSnapshot,
    CiSummary,
)
from qstatus.commands import CommandResult, run_command
from qstatus.git_snapshot import collect_repo_snapshot

if TYPE_CHECKING:
    from pathlib import Path

    from qstatus.models import BranchState, ChangeSummary, CommandRecord, RepoIdentity


DEFAULT_RUN_LIMIT = 20
MAX_FAILED_RUNS = 3
MAX_FAILED_JOBS = 5
MAX_LOG_TAIL_LINES = 120
MAX_LOG_LINE_CHARS = 300
MAX_LOG_TOTAL_CHARS = 25_000


class _CommandCollector:
    """Small helper that captures command evidence when requested."""

    def __init__(self, root: Path, *, include_commands: bool) -> None:
        self.root = root
        self.include_commands = include_commands
        self.records: list[CommandRecord] = []

    def run(self, args: list[str], *, timeout_s: float = 8.0) -> CommandResult:
        """Run a command and optionally store compact evidence."""
        result = run_command(args, cwd=self.root, timeout_s=timeout_s)
        if self.include_commands:
            self.records.append(result.evidence())
        return result

    def gh(self, args: list[str], *, timeout_s: float = 8.0) -> CommandResult:
        """Run a GitHub CLI command."""
        return self.run(["gh", *args], timeout_s=timeout_s)


def collect_ci_snapshot(
    cwd: Path,
    *,
    include_commands: bool = False,
    log_tail: int | None = None,
) -> CiSnapshot:
    """Collect read-only CI facts for the repository at cwd."""
    repo_snapshot = collect_repo_snapshot(
        cwd,
        include_github=False,
        include_commands=include_commands,
    )
    root = cwd_for_snapshot(repo_snapshot.repo)
    collector = _CommandCollector(root, include_commands=include_commands)
    source_errors: list[str] = []
    github_repo = repo_snapshot.repo.github_repo
    upstream_oid = _resolve_upstream_tracking_oid(
        collector,
        repo_snapshot.branch.upstream,
    )
    if not github_repo:
        commits = _build_commit_refs(
            branch=repo_snapshot.branch,
            upstream_oid=upstream_oid,
            pull_request=None,
            expected_oid=repo_snapshot.branch.oid,
            expected_source="local-head",
        )
        currentness = CiCurrentness(
            state="unknown",
            reason="no-github-remote",
            expected_oid=commits.expected_oid,
            checked_oid=None,
            source="github",
        )
        summary = _summarize([], [], currentness.state, failing_jobs=0)
        return CiSnapshot(
            schema_version=CI_SCHEMA_VERSION,
            repo=repo_snapshot.repo,
            branch=repo_snapshot.branch,
            changes=repo_snapshot.changes,
            github=CiGitHubStatus(
                status="unavailable",
                repo=None,
                error="no GitHub remote detected",
            ),
            pull_request=None,
            commits=commits,
            currentness=currentness,
            summary=summary,
            source_errors=["no GitHub remote detected"],
            commands=[*repo_snapshot.commands, *collector.records],
        )

    auth_result = collector.gh(["auth", "status"], timeout_s=5.0)
    if auth_result.unavailable:
        return _unavailable_snapshot(
            repo_snapshot.repo,
            repo_snapshot.branch,
            repo_snapshot.changes,
            repo_snapshot.commands,
            collector.records,
            github_repo,
            upstream_oid,
            "gh is not installed",
        )
    if not auth_result.ok:
        detail = auth_result.stderr.strip() or auth_result.stdout.strip()
        return _unavailable_snapshot(
            repo_snapshot.repo,
            repo_snapshot.branch,
            repo_snapshot.changes,
            repo_snapshot.commands,
            collector.records,
            github_repo,
            upstream_oid,
            f"gh auth unavailable: {detail}",
        )

    pull_request = _collect_pull_request(collector, github_repo, repo_snapshot.branch)
    expected_oid, expected_source = _expected_commit(repo_snapshot.branch, pull_request)
    commits = _build_commit_refs(
        branch=repo_snapshot.branch,
        upstream_oid=upstream_oid,
        pull_request=pull_request,
        expected_oid=expected_oid,
        expected_source=expected_source,
    )

    checks: list[CiCheck] = []
    if pull_request is not None:
        checks = _collect_pr_checks(
            collector,
            repo=github_repo,
            pull_request=pull_request,
            expected_oid=expected_oid,
            source_errors=source_errors,
        )

    runs = _collect_runs(
        collector,
        repo=github_repo,
        branch=repo_snapshot.branch,
        expected_oid=expected_oid,
        source_errors=source_errors,
    )
    currentness = _classify_currentness(
        branch=repo_snapshot.branch,
        pull_request=pull_request,
        expected_oid=expected_oid,
        expected_source=expected_source,
        runs=runs,
    )
    jobs = _collect_failed_jobs(
        collector,
        repo=github_repo,
        runs=runs,
        source_errors=source_errors,
    )
    log_tails = _collect_log_tails(
        collector,
        repo=github_repo,
        runs=runs,
        log_tail=log_tail,
    )
    summary = _summarize(checks, runs, currentness.state, failing_jobs=len(jobs))

    return CiSnapshot(
        schema_version=CI_SCHEMA_VERSION,
        repo=repo_snapshot.repo,
        branch=repo_snapshot.branch,
        changes=repo_snapshot.changes,
        github=CiGitHubStatus(status="available", repo=github_repo),
        pull_request=pull_request,
        commits=commits,
        currentness=currentness,
        checks=checks,
        runs=runs,
        jobs=jobs,
        log_tails=log_tails,
        summary=summary,
        source_errors=source_errors,
        commands=[*repo_snapshot.commands, *collector.records],
    )


def cwd_for_snapshot(repo: RepoIdentity) -> Path:
    """Return the root path for command collection."""
    from pathlib import Path

    return Path(repo.root)


def validate_log_tail(value: int | None) -> int | None:
    """Normalize and validate the optional log-tail line count."""
    if value is None:
        return None
    if value <= 0:
        msg = "--log-tail must be greater than zero"
        raise ValueError(msg)
    if value > MAX_LOG_TAIL_LINES:
        msg = f"--log-tail must be at most {MAX_LOG_TAIL_LINES}"
        raise ValueError(msg)
    return value


def _unavailable_snapshot(
    repo: RepoIdentity,
    branch: BranchState,
    changes: ChangeSummary,
    repo_commands: list[CommandRecord],
    gh_commands: list[CommandRecord],
    github_repo: str,
    upstream_oid: str | None,
    error: str,
) -> CiSnapshot:
    commits = _build_commit_refs(
        branch=branch,
        upstream_oid=upstream_oid,
        pull_request=None,
        expected_oid=branch.oid,
        expected_source="local-head",
    )
    currentness = CiCurrentness(
        state="unknown",
        reason="github-unavailable",
        expected_oid=commits.expected_oid,
        checked_oid=None,
        source="github",
    )
    summary = _summarize([], [], currentness.state, failing_jobs=0)
    return CiSnapshot(
        schema_version=CI_SCHEMA_VERSION,
        repo=repo,
        branch=branch,
        changes=changes,
        github=CiGitHubStatus(status="unavailable", repo=github_repo, error=error),
        pull_request=None,
        commits=commits,
        currentness=currentness,
        summary=summary,
        source_errors=[error],
        commands=[*repo_commands, *gh_commands],
    )


def _resolve_upstream_tracking_oid(
    collector: _CommandCollector,
    upstream: str | None,
) -> str | None:
    if not upstream:
        return None
    result = collector.run(["git", "rev-parse", "--verify", upstream], timeout_s=3.0)
    if not result.ok:
        return None
    value = result.stdout.strip()
    return value or None


def _collect_pull_request(
    collector: _CommandCollector,
    repo: str,
    branch: BranchState,
) -> CiPullRequest | None:
    if branch.head in {"unknown", "(detached)"}:
        return None
    fields = (
        "number,title,url,state,isDraft,baseRefName,baseRefOid,headRefName,"
        "headRefOid,reviewDecision,statusCheckRollup"
    )
    result = collector.gh(
        [
            "pr",
            "view",
            branch.head,
            "--repo",
            repo,
            "--json",
            fields,
        ],
    )
    if result.ok:
        data = _loads_object(result.stdout)
        if data is not None:
            return _pull_request_from_mapping(data)
    return _collect_pull_request_from_status(collector, repo, branch.head, fields)


def _collect_pull_request_from_status(
    collector: _CommandCollector,
    repo: str,
    branch_name: str,
    fields: str,
) -> CiPullRequest | None:
    result = collector.gh(["pr", "status", "--repo", repo, "--json", fields])
    if result.ok:
        data = _loads_object(result.stdout)
        if data is not None:
            pull_request = _pull_request_from_status_data(data, branch_name)
            if pull_request is not None:
                return pull_request
    result = collector.gh(
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
            fields,
        ],
    )
    if not result.ok:
        return None
    items = _loads_list(result.stdout)
    if not items:
        return None
    return _pull_request_from_mapping(items[0])


def _pull_request_from_status_data(
    data: dict[str, Any],
    branch_name: str,
) -> CiPullRequest | None:
    for value in data.values():
        if isinstance(value, dict) and value.get("headRefName") == branch_name:
            return _pull_request_from_mapping(value)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("headRefName") == branch_name:
                    return _pull_request_from_mapping(item)
    return None


def _pull_request_from_mapping(data: dict[str, Any]) -> CiPullRequest:
    return CiPullRequest(
        number=int(data.get("number", 0)),
        title=str(data.get("title") or ""),
        url=str(data.get("url") or ""),
        state=str(data.get("state") or "UNKNOWN").lower(),
        is_draft=bool(data.get("isDraft")),
        base_ref=_optional_str(data.get("baseRefName")),
        base_oid=_optional_str(data.get("baseRefOid")),
        head_ref=_optional_str(data.get("headRefName")),
        head_oid=_optional_str(data.get("headRefOid")),
        review_decision=_optional_str(data.get("reviewDecision")),
    )


def _expected_commit(
    branch: BranchState,
    pull_request: CiPullRequest | None,
) -> tuple[str | None, str]:
    if (
        pull_request is not None
        and pull_request.state == "open"
        and pull_request.head_oid
    ):
        return pull_request.head_oid, "pr-head"
    return branch.oid, "local-head"


def _build_commit_refs(
    *,
    branch: BranchState,
    upstream_oid: str | None,
    pull_request: CiPullRequest | None,
    expected_oid: str | None,
    expected_source: str,
) -> CiCommitRefs:
    pr_head_oid = pull_request.head_oid if pull_request else None
    return CiCommitRefs(
        local_head=branch.oid,
        local_short=branch.short_oid,
        branch=branch.head,
        upstream=branch.upstream,
        upstream_tracking_oid=upstream_oid,
        pr_head_oid=pr_head_oid,
        pr_base_oid=pull_request.base_oid if pull_request else None,
        expected_oid=expected_oid,
        expected_source=expected_source,
        local_matches_pr=_matches(branch.oid, pr_head_oid),
        local_matches_upstream_tracking=_matches(branch.oid, upstream_oid),
    )


def _collect_pr_checks(
    collector: _CommandCollector,
    *,
    repo: str,
    pull_request: CiPullRequest,
    expected_oid: str | None,
    source_errors: list[str],
) -> list[CiCheck]:
    result = collector.gh(
        [
            "pr",
            "checks",
            str(pull_request.number),
            "--repo",
            repo,
            "--json",
            "bucket,completedAt,description,event,link,name,startedAt,state,workflow",
        ],
    )
    items = _loads_list(result.stdout)
    if items is None:
        if not result.ok:
            source_errors.append(_source_error("pr-checks", result))
        return []
    currentness = _item_currentness(pull_request.head_oid, expected_oid)
    return [
        CiCheck(
            name=str(item.get("name") or "unknown"),
            workflow=_optional_str(item.get("workflow")),
            status=_optional_str(item.get("state")),
            conclusion=_optional_str(item.get("state")),
            bucket=_normalized_bucket(item.get("bucket")),
            started_at=_optional_str(item.get("startedAt")),
            completed_at=_optional_str(item.get("completedAt")),
            event=_optional_str(item.get("event")),
            url=_optional_str(item.get("link")),
            details_url=_optional_str(item.get("link")),
            head_sha=pull_request.head_oid,
            source="pr-checks",
            currentness=currentness,
        )
        for item in items
    ]


def _collect_runs(
    collector: _CommandCollector,
    *,
    repo: str,
    branch: BranchState,
    expected_oid: str | None,
    source_errors: list[str],
) -> list[CiRun]:
    runs_by_id: dict[int, CiRun] = {}
    if expected_oid:
        _add_runs(
            runs_by_id,
            _run_list(
                collector,
                repo=repo,
                args=["--commit", expected_oid],
                expected_oid=expected_oid,
                source_errors=source_errors,
            ),
        )
    if branch.head not in {"unknown", "(detached)"}:
        _add_runs(
            runs_by_id,
            _run_list(
                collector,
                repo=repo,
                args=["--branch", branch.head],
                expected_oid=expected_oid,
                source_errors=source_errors,
            ),
        )
    runs = list(runs_by_id.values())
    runs.sort(key=lambda run: run.created_at or "", reverse=True)
    runs.sort(
        key=lambda run: (run.currentness != "current", _bucket_sort_key(run.bucket))
    )
    return runs


def _run_list(
    collector: _CommandCollector,
    *,
    repo: str,
    args: list[str],
    expected_oid: str | None,
    source_errors: list[str],
) -> list[CiRun]:
    result = collector.gh(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--limit",
            str(DEFAULT_RUN_LIMIT),
            "--json",
            (
                "databaseId,status,conclusion,headSha,headBranch,workflowName,"
                "displayTitle,event,createdAt,updatedAt,url,attempt"
            ),
            *args,
        ],
    )
    if not result.ok:
        source_errors.append(_source_error("run-list", result))
        return []
    items = _loads_list(result.stdout)
    if items is None:
        source_errors.append("run-list: invalid JSON")
        return []
    return [_run_from_mapping(item, expected_oid=expected_oid) for item in items]


def _run_from_mapping(data: dict[str, Any], *, expected_oid: str | None) -> CiRun:
    status = _optional_str(data.get("status"))
    conclusion = _optional_str(data.get("conclusion"))
    head_sha = _optional_str(data.get("headSha"))
    return CiRun(
        database_id=_optional_int(data.get("databaseId")),
        workflow_name=_optional_str(data.get("workflowName")),
        display_title=_optional_str(data.get("displayTitle")),
        event=_optional_str(data.get("event")),
        status=status,
        conclusion=conclusion,
        bucket=_bucket_for(status=status, conclusion=conclusion),
        head_sha=head_sha,
        head_branch=_optional_str(data.get("headBranch")),
        created_at=_optional_str(data.get("createdAt")),
        updated_at=_optional_str(data.get("updatedAt")),
        url=_optional_str(data.get("url")),
        attempt=_optional_int(data.get("attempt")),
        currentness=_item_currentness(head_sha, expected_oid),
    )


def _add_runs(target: dict[int, CiRun], runs: list[CiRun]) -> None:
    for run in runs:
        if run.database_id is None:
            continue
        current = target.get(run.database_id)
        if current is None or (
            current.currentness != "current" and run.currentness == "current"
        ):
            target[run.database_id] = run


def _classify_currentness(
    *,
    branch: BranchState,
    pull_request: CiPullRequest | None,
    expected_oid: str | None,
    expected_source: str,
    runs: list[CiRun],
) -> CiCurrentness:
    if expected_source == "pr-head" and pull_request is not None:
        if _matches(branch.oid, pull_request.head_oid) is True:
            return CiCurrentness(
                state="current",
                reason="local-head-matches-pr-head",
                expected_oid=expected_oid,
                checked_oid=pull_request.head_oid,
                source="pr-head",
            )
        return CiCurrentness(
            state="stale",
            reason="local-head-differs-from-pr-head",
            expected_oid=expected_oid,
            checked_oid=pull_request.head_oid,
            source="pr-head",
        )

    current_run = next((run for run in runs if run.currentness == "current"), None)
    if current_run is not None:
        return CiCurrentness(
            state="current",
            reason="run-exists-for-expected-sha",
            expected_oid=expected_oid,
            checked_oid=current_run.head_sha,
            source="run-list-commit",
        )
    stale_run = next((run for run in runs if run.head_sha), None)
    if stale_run is not None:
        return CiCurrentness(
            state="stale",
            reason="latest-run-is-not-for-expected-sha",
            expected_oid=expected_oid,
            checked_oid=stale_run.head_sha,
            source="run-list-branch",
        )
    return CiCurrentness(
        state="absent",
        reason="no-run-for-expected-sha",
        expected_oid=expected_oid,
        checked_oid=None,
        source="run-list",
    )


def _collect_failed_jobs(
    collector: _CommandCollector,
    *,
    repo: str,
    runs: list[CiRun],
    source_errors: list[str],
) -> list[CiJob]:
    failed_current_runs = [
        run
        for run in runs
        if run.currentness == "current" and run.bucket in {"fail", "cancel"}
    ][:MAX_FAILED_RUNS]
    jobs: list[CiJob] = []
    for run in failed_current_runs:
        if run.database_id is None:
            continue
        result = collector.gh(
            [
                "run",
                "view",
                str(run.database_id),
                "--repo",
                repo,
                "--json",
                (
                    "databaseId,jobs,url,status,conclusion,headSha,workflowName,"
                    "displayTitle"
                ),
            ],
        )
        if not result.ok:
            source_errors.append(_source_error("run-view", result))
            continue
        data = _loads_object(result.stdout)
        if data is None:
            source_errors.append("run-view: invalid JSON")
            continue
        for item in _jobs_from_run_data(data, run_database_id=run.database_id):
            if item.bucket in {"fail", "cancel"}:
                jobs.append(item)
                if len(jobs) >= MAX_FAILED_JOBS:
                    return jobs
    return jobs


def _jobs_from_run_data(
    data: dict[str, Any],
    *,
    run_database_id: int | None,
) -> list[CiJob]:
    raw_jobs = data.get("jobs")
    if not isinstance(raw_jobs, list):
        return []
    jobs: list[CiJob] = []
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
        status = _optional_str(item.get("status"))
        conclusion = _optional_str(item.get("conclusion"))
        jobs.append(
            CiJob(
                database_id=_optional_int(item.get("databaseId")),
                run_database_id=run_database_id,
                name=str(item.get("name") or "unknown"),
                status=status,
                conclusion=conclusion,
                bucket=_bucket_for(status=status, conclusion=conclusion),
                started_at=_optional_str(item.get("startedAt")),
                completed_at=_optional_str(item.get("completedAt")),
                url=_optional_str(item.get("url")),
            )
        )
    return jobs


def _collect_log_tails(
    collector: _CommandCollector,
    *,
    repo: str,
    runs: list[CiRun],
    log_tail: int | None,
) -> list[CiLogTail]:
    if log_tail is None:
        return []
    failed_current_runs = [
        run
        for run in runs
        if run.currentness == "current" and run.bucket in {"fail", "cancel"}
    ][:MAX_FAILED_RUNS]
    tails: list[CiLogTail] = []
    for run in failed_current_runs:
        if run.database_id is None:
            continue
        result = collector.gh(
            [
                "run",
                "view",
                str(run.database_id),
                "--repo",
                repo,
                "--log-failed",
            ],
            timeout_s=15.0,
        )
        if not result.ok:
            tails.append(
                CiLogTail(
                    run_database_id=run.database_id,
                    status="unavailable",
                    requested_lines=log_tail,
                    capped=False,
                    reason=_bounded_error(result),
                )
            )
            continue
        lines, capped = _tail_log_lines(result.stdout, requested_lines=log_tail)
        if not lines:
            tails.append(
                CiLogTail(
                    run_database_id=run.database_id,
                    status="unavailable",
                    requested_lines=log_tail,
                    capped=False,
                    reason="failed-log-fetch-empty",
                )
            )
            continue
        tails.append(
            CiLogTail(
                run_database_id=run.database_id,
                status="available",
                requested_lines=log_tail,
                capped=capped,
                lines=lines,
            )
        )
    return tails


def _tail_log_lines(stdout: str, *, requested_lines: int) -> tuple[list[str], bool]:
    raw_lines = [line.rstrip() for line in stdout.splitlines() if line.strip()]
    selected = raw_lines[-requested_lines:]
    capped = len(raw_lines) > requested_lines
    output: list[str] = []
    total_chars = 0
    for line in selected:
        clean_line = line[:MAX_LOG_LINE_CHARS]
        if len(clean_line) < len(line):
            capped = True
        total_chars += len(clean_line)
        if total_chars > MAX_LOG_TOTAL_CHARS:
            capped = True
            break
        output.append(clean_line)
    return output, capped


def _summarize(
    checks: list[CiCheck],
    runs: list[CiRun],
    currentness: str,
    *,
    failing_jobs: int,
) -> CiSummary:
    items = checks if checks else runs
    counts = {
        "pass": 0,
        "fail": 0,
        "pending": 0,
        "running": 0,
        "skipping": 0,
        "cancel": 0,
        "unknown": 0,
    }
    for item in items:
        counts[item.bucket if item.bucket in counts else "unknown"] += 1
    state = _summary_state(counts, total=len(items))
    failing_runs = sum(1 for run in runs if run.bucket in {"fail", "cancel"})
    return CiSummary(
        ci_state=state,
        currentness=currentness,
        total_checks=len(items),
        pass_count=counts["pass"],
        fail_count=counts["fail"],
        pending_count=counts["pending"],
        running_count=counts["running"],
        skipped_count=counts["skipping"],
        cancel_count=counts["cancel"],
        unknown_count=counts["unknown"],
        failing_runs=failing_runs,
        failing_jobs=failing_jobs,
    )


def _summary_state(counts: dict[str, int], *, total: int) -> str:
    if total == 0:
        return "none"
    if counts["fail"]:
        return "failure"
    if counts["cancel"]:
        return "cancelled"
    if counts["running"]:
        return "running"
    if counts["pending"]:
        return "pending"
    if counts["unknown"] == total:
        return "unknown"
    if counts["pass"] == total:
        return "success"
    if counts["skipping"] == total:
        return "skipped"
    if (
        counts["pass"]
        and counts["skipping"]
        and counts["pass"] + counts["skipping"] == total
    ):
        return "success"
    return "mixed"


def _bucket_for(*, status: str | None, conclusion: str | None) -> str:
    raw_status = (status or "").lower()
    raw_conclusion = (conclusion or "").lower()
    if raw_status == "completed":
        if raw_conclusion == "success":
            return "pass"
        if raw_conclusion in {
            "failure",
            "timed_out",
            "startup_failure",
            "action_required",
        }:
            return "fail"
        if raw_conclusion == "cancelled":
            return "cancel"
        if raw_conclusion in {"skipped", "neutral"}:
            return "skipping"
        return "unknown"
    if raw_status in {"in_progress"}:
        return "running"
    if raw_status in {"queued", "pending", "requested", "waiting"}:
        return "pending"
    if raw_conclusion:
        return _bucket_for(status="completed", conclusion=raw_conclusion)
    return "unknown"


def _normalized_bucket(value: object) -> str:
    bucket = str(value or "").lower()
    if bucket == "pass":
        return "pass"
    if bucket == "fail":
        return "fail"
    if bucket == "pending":
        return "pending"
    if bucket == "skipping":
        return "skipping"
    if bucket == "cancel":
        return "cancel"
    return "unknown"


def _item_currentness(item_oid: str | None, expected_oid: str | None) -> str:
    if not item_oid or not expected_oid:
        return "unknown"
    return "current" if item_oid == expected_oid else "stale"


def _matches(left: str | None, right: str | None) -> bool | None:
    if left is None or right is None:
        return None
    return left == right


def _source_error(source: str, result: CommandResult) -> str:
    return f"{source}: {_bounded_error(result)}"


def _bounded_error(result: CommandResult) -> str:
    detail = result.stderr.strip() or result.stdout.strip()
    if not detail:
        detail = f"exit code {result.exit_code}"
    return detail.replace("\n", " ")[:300]


def _bucket_sort_key(bucket: str) -> int:
    order = {
        "fail": 0,
        "cancel": 1,
        "running": 2,
        "pending": 3,
        "unknown": 4,
        "pass": 5,
        "skipping": 6,
    }
    return order.get(bucket, 7)


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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except ValueError:
        return None
