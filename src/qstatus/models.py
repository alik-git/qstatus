"""Data models for qstatus repo snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SCHEMA_VERSION = "qstatus_repo_snapshot_v1"
ENV_SCHEMA_VERSION = "qstatus_env_snapshot_v1"


@dataclass(frozen=True, slots=True)
class CommandRecord:
    """Small command evidence record for verbose/debug output."""

    args: list[str]
    cwd: str
    exit_code: int | None
    timed_out: bool = False
    unavailable: bool = False
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class ToolFact:
    """Availability and version facts for one optional executable."""

    name: str
    available: bool
    path: str | None = None
    realpath: str | None = None
    version: str | None = None
    status: str = "not_found"
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ShellState:
    """Selected shell environment facts relevant to Python environment layering."""

    cwd: str
    kind: str
    conda_active: bool
    conda_default_env: str | None = None
    conda_prefix: str | None = None
    conda_shlvl: str | None = None
    virtual_env: str | None = None
    venv_active: bool = False


@dataclass(frozen=True, slots=True)
class PythonRuntimeInfo:
    """The Python runtime that is currently executing qstatus."""

    executable: str
    version: str
    implementation: str
    prefix: str
    base_prefix: str
    venv_like: bool


@dataclass(frozen=True, slots=True)
class ProjectEnvironment:
    """Project-local environment files and Python project metadata."""

    cwd: str
    root: str
    root_source: str
    name: str
    pyproject_path: str | None = None
    pyproject_name: str | None = None
    requires_python: str | None = None
    pyproject_status: str = "missing"
    pyproject_error: str | None = None
    uv_lock: bool = False
    requirements_txt: bool = False
    python_version_file: bool = False
    environment_yml: bool = False
    conda_lock_yml: bool = False
    venv_path: str | None = None
    venv_exists: bool = False
    venv_python_exists: bool = False


@dataclass(frozen=True, slots=True)
class DevpyProject:
    """Facts parsed from a project's devpy.toml file."""

    present: bool
    path: str | None = None
    status: str = "missing"
    error: str | None = None
    base_conda_env: str | None = None
    venv_path: str | None = None
    venv_exists: bool = False
    venv_python_exists: bool = False
    editable_count: int = 0
    editable_paths: list[str] = field(default_factory=list)
    install_deps: bool | None = None


@dataclass(frozen=True, slots=True)
class EnvSnapshot:
    """Full qstatus environment snapshot."""

    schema_version: str
    shell: ShellState
    runtime: PythonRuntimeInfo
    python_commands: dict[str, ToolFact]
    project: ProjectEnvironment
    devpy: DevpyProject
    tools: dict[str, ToolFact]
    hints: dict[str, list[str]] = field(default_factory=dict)
    commands: list[CommandRecord] = field(default_factory=list)

    def to_dict(self, *, include_commands: bool = False) -> dict[str, object]:
        """Convert the environment snapshot into stable JSON."""
        payload = asdict(self)
        if not include_commands:
            payload.pop("commands", None)
        return payload


@dataclass(frozen=True, slots=True)
class RemoteInfo:
    """Git remote fetch/push URLs."""

    name: str
    fetch_url: str | None = None
    push_url: str | None = None


@dataclass(frozen=True, slots=True)
class RepoIdentity:
    """Repository identity and location facts."""

    root: str
    git_dir: str
    name: str
    remotes: list[RemoteInfo] = field(default_factory=list)
    github_repo: str | None = None


@dataclass(frozen=True, slots=True)
class BranchState:
    """Current HEAD, branch, upstream, and local tracking facts."""

    head: str
    oid: str | None
    short_oid: str | None
    upstream: str | None
    ahead: int | None
    behind: int | None
    sync_state: str
    commit_subject: str | None = None


@dataclass(frozen=True, slots=True)
class ChangeSummary:
    """Local working tree change counts from Git porcelain output."""

    staged: int
    unstaged: int
    untracked: int
    conflicted: int
    stash_count: int | None
    worktree_state: str
    tracked_entries: int
    diff_shortstat: str | None = None
    cached_diff_shortstat: str | None = None


@dataclass(frozen=True, slots=True)
class WorktreeEntry:
    """One entry from `git worktree list --porcelain`."""

    path: str
    head: str | None
    branch: str | None
    bare: bool = False
    detached: bool = False
    prunable: bool = False


@dataclass(frozen=True, slots=True)
class WorktreeState:
    """Current repo worktree list summary."""

    current_path: str
    worktrees: list[WorktreeEntry]
    count: int


@dataclass(frozen=True, slots=True)
class SubmoduleSummary:
    """Submodule state summary."""

    present: bool
    total: int = 0
    clean: int = 0
    changed: int = 0
    uninitialized: int = 0
    conflicted: int = 0
    unknown: int = 0


@dataclass(frozen=True, slots=True)
class PullRequestInfo:
    """GitHub pull request facts for the current branch."""

    number: int
    title: str
    url: str
    state: str
    is_draft: bool
    base_ref: str | None
    head_ref: str | None
    review_decision: str | None


@dataclass(frozen=True, slots=True)
class RemoteCheckSummary:
    """GitHub check and workflow-run state summary."""

    state: str
    total: int = 0
    success: int = 0
    failure: int = 0
    pending: int = 0
    running: int = 0
    skipped: int = 0
    unknown: int = 0
    head_sha: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """GitHub release facts for the current package version."""

    version: str | None
    tag: str | None
    exists: bool | None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubContext:
    """Optional GitHub PR, CI, and release facts."""

    status: str
    repo: str | None = None
    pr_state: str = "unknown"
    pull_request: PullRequestInfo | None = None
    checks: RemoteCheckSummary | None = None
    release: ReleaseInfo | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RepoSummary:
    """Neutral repo status summaries derived from factual fields."""

    sync_state: str
    worktree_state: str
    pr_state: str
    remote_check_state: str


@dataclass(frozen=True, slots=True)
class RepoSnapshot:
    """Full qstatus repo snapshot."""

    schema_version: str
    repo: RepoIdentity
    branch: BranchState
    changes: ChangeSummary
    worktree: WorktreeState
    submodules: SubmoduleSummary
    github: GitHubContext
    summary: RepoSummary
    commands: list[CommandRecord] = field(default_factory=list)

    def to_dict(self, *, include_commands: bool = False) -> dict[str, object]:
        """Convert the snapshot into a stable JSON-serializable mapping."""
        payload = asdict(self)
        if not include_commands:
            payload.pop("commands", None)
        return payload
