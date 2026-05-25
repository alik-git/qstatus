"""Data models for qstatus CI snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qstatus.models import BranchState, ChangeSummary, CommandRecord, RepoIdentity

CI_SCHEMA_VERSION = "qstatus_ci_snapshot_v1"


@dataclass(frozen=True, slots=True)
class CiGitHubStatus:
    """GitHub availability facts for a CI snapshot."""

    status: str
    repo: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CiPullRequest:
    """Pull request facts needed for CI currentness."""

    number: int
    title: str
    url: str
    state: str
    is_draft: bool
    base_ref: str | None
    base_oid: str | None
    head_ref: str | None
    head_oid: str | None
    review_decision: str | None = None


@dataclass(frozen=True, slots=True)
class CiCommitRefs:
    """Local, PR, and expected commit facts for CI checks."""

    local_head: str | None
    local_short: str | None
    branch: str
    upstream: str | None
    upstream_tracking_oid: str | None
    pr_head_oid: str | None
    pr_base_oid: str | None
    expected_oid: str | None
    expected_source: str
    local_matches_pr: bool | None
    local_matches_upstream_tracking: bool | None


@dataclass(frozen=True, slots=True)
class CiCurrentness:
    """Whether the CI evidence applies to the expected commit."""

    state: str
    reason: str
    expected_oid: str | None
    checked_oid: str | None
    source: str


@dataclass(frozen=True, slots=True)
class CiCheck:
    """One check row from GitHub PR checks."""

    name: str
    workflow: str | None
    status: str | None
    conclusion: str | None
    bucket: str
    started_at: str | None
    completed_at: str | None
    event: str | None
    url: str | None
    details_url: str | None
    head_sha: str | None
    source: str
    currentness: str


@dataclass(frozen=True, slots=True)
class CiRun:
    """One GitHub Actions workflow run row."""

    database_id: int | None
    workflow_name: str | None
    display_title: str | None
    event: str | None
    status: str | None
    conclusion: str | None
    bucket: str
    head_sha: str | None
    head_branch: str | None
    created_at: str | None
    updated_at: str | None
    url: str | None
    attempt: int | None
    currentness: str


@dataclass(frozen=True, slots=True)
class CiJob:
    """One job row from a GitHub Actions workflow run."""

    database_id: int | None
    run_database_id: int | None
    name: str
    status: str | None
    conclusion: str | None
    bucket: str
    started_at: str | None
    completed_at: str | None
    url: str | None


@dataclass(frozen=True, slots=True)
class CiLogTail:
    """Bounded tail of failed GitHub Actions log output."""

    run_database_id: int | None
    status: str
    requested_lines: int
    capped: bool
    lines: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CiSummary:
    """Aggregate CI state for compact human output."""

    ci_state: str
    currentness: str
    total_checks: int
    pass_count: int = 0
    fail_count: int = 0
    pending_count: int = 0
    running_count: int = 0
    skipped_count: int = 0
    cancel_count: int = 0
    unknown_count: int = 0
    failing_runs: int = 0
    failing_jobs: int = 0


@dataclass(frozen=True, slots=True)
class CiSnapshot:
    """Full qstatus CI snapshot."""

    schema_version: str
    repo: RepoIdentity
    branch: BranchState
    changes: ChangeSummary
    github: CiGitHubStatus
    pull_request: CiPullRequest | None
    commits: CiCommitRefs
    currentness: CiCurrentness
    checks: list[CiCheck] = field(default_factory=list)
    runs: list[CiRun] = field(default_factory=list)
    jobs: list[CiJob] = field(default_factory=list)
    log_tails: list[CiLogTail] = field(default_factory=list)
    summary: CiSummary | None = None
    source_errors: list[str] = field(default_factory=list)
    commands: list[CommandRecord] = field(default_factory=list)

    def to_dict(self, *, include_commands: bool = False) -> dict[str, object]:
        """Convert the CI snapshot into stable JSON."""
        payload = asdict(self)
        if not include_commands:
            payload.pop("commands", None)
        return payload
