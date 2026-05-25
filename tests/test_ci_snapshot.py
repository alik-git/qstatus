"""Tests for qstatus CI snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import qstatus.ci_snapshot
from qstatus.ci_render import render_ci_human
from qstatus.cli import main
from qstatus.commands import CommandResult, run_command

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def test_cli_ci_json_reports_missing_github_remote(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A local repo without a GitHub remote should produce unavailable CI facts."""
    repo = _repo(tmp_path)

    assert main(["ci", "--cwd", str(repo), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "qstatus_ci_snapshot_v1"
    assert payload["github"]["status"] == "unavailable"
    assert payload["github"]["error"] == "no GitHub remote detected"
    assert payload["currentness"]["state"] == "unknown"


def test_cli_ci_non_repo_json_exits_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-repo qstatus ci target should use the normal qstatus error code."""
    assert main(["ci", "--cwd", str(tmp_path), "--json"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "qstatus_error_v1"
    assert "not a git worktree" in payload["error"]


def test_ci_current_pr_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collect current PR checks and current run URL for the local head."""
    repo = _repo(tmp_path, remote=True, branch="feature")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=head,
            pr_checks=[{"bucket": "pass", "name": "Python", "workflow": "Checks"}],
            runs=[
                {
                    "databaseId": 101,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/101",
                }
            ],
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo)
    assert snapshot.currentness.state == "current"
    assert snapshot.commits.local_matches_pr is True
    assert snapshot.changes.worktree_state == "clean"
    assert snapshot.summary is not None
    assert snapshot.summary.ci_state == "success"
    assert (
        snapshot.runs[0].url == "https://github.com/alik-git/qstatus/actions/runs/101"
    )


def test_ci_stale_pr_success_renders_stale_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A green PR check for a different PR head must not look current."""
    repo = _repo(tmp_path, remote=True, branch="feature")
    head = _git(repo, "rev-parse", "HEAD")
    pr_head = "f" * 40

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=pr_head,
            pr_checks=[{"bucket": "pass", "name": "Python", "workflow": "Checks"}],
            runs=[
                {
                    "databaseId": 102,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": pr_head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/102",
                }
            ],
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo)

    assert snapshot.currentness.state == "stale"
    assert snapshot.commits.local_matches_pr is False
    output = render_ci_human(snapshot)
    assert "STATE clean" in output
    assert "CURRENT stale" in output
    assert "CHECKS stale-success" in output


def test_ci_human_output_shows_dirty_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI output should not hide local changes that are not in remote CI."""
    repo = _repo(tmp_path, remote=True, branch="feature")
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "dirty.txt").write_text("not checked by CI yet\n")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=head,
            pr_checks=[{"bucket": "pass", "name": "Python", "workflow": "Checks"}],
            runs=[
                {
                    "databaseId": 106,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/106",
                }
            ],
        ),
    )

    output = render_ci_human(qstatus.ci_snapshot.collect_ci_snapshot(repo))

    assert "CURRENT current" in output
    assert "CHECKS success" in output
    assert "STATE dirty" in output
    assert "untracked=1" in output


def test_ci_no_pr_uses_local_head_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A no-PR branch should use local HEAD and commit runs."""
    repo = _repo(tmp_path, remote=True, branch="main")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=None,
            pr_checks=[],
            runs=[
                {
                    "databaseId": 103,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "success",
                    "headSha": head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/103",
                }
            ],
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo)

    assert snapshot.pull_request is None
    assert snapshot.commits.expected_oid == head
    assert snapshot.currentness.state == "current"
    assert snapshot.summary is not None
    assert snapshot.summary.ci_state == "success"


def test_ci_no_pr_without_expected_run_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No PR and no run for local HEAD should be explicit absent CI evidence."""
    repo = _repo(tmp_path, remote=True, branch="main")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(head=head, pr_head=None, pr_checks=[], runs=[]),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo)

    assert snapshot.currentness.state == "absent"
    assert snapshot.currentness.reason == "no-run-for-expected-sha"
    assert snapshot.summary is not None
    assert snapshot.summary.ci_state == "none"


def test_ci_cancelled_run_renders_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelled runs should remain visibly cancelled, not pass or fail."""
    repo = _repo(tmp_path, remote=True, branch="main")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=None,
            pr_checks=[],
            runs=[
                {
                    "databaseId": 107,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "cancelled",
                    "headSha": head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/107",
                }
            ],
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo)
    output = render_ci_human(snapshot)

    assert snapshot.summary is not None
    assert snapshot.summary.ci_state == "cancelled"
    assert "RUNS cancelled" in output
    assert "RUN Checks cancelled" in output


def test_ci_pr_check_buckets_are_counted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR check buckets should be counted without GitHub Actions job lookup."""
    repo = _repo(tmp_path, remote=True, branch="feature")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=head,
            pr_checks=[
                {"bucket": "pass", "name": "Python", "workflow": "Checks"},
                {"bucket": "fail", "name": "Docs", "workflow": "Checks"},
                {"bucket": "pending", "name": "Lint", "workflow": "Checks"},
                {"bucket": "skipping", "name": "Optional", "workflow": "Checks"},
                {"bucket": "cancel", "name": "Old", "workflow": "Checks"},
            ],
            runs=[],
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo)

    assert snapshot.summary is not None
    assert snapshot.summary.total_checks == 5
    assert snapshot.summary.pass_count == 1
    assert snapshot.summary.fail_count == 1
    assert snapshot.summary.pending_count == 1
    assert snapshot.summary.skipped_count == 1
    assert snapshot.summary.cancel_count == 1


def test_ci_failed_run_collects_jobs_and_log_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed current runs should include failed jobs and optional dumb log tails."""
    repo = _repo(tmp_path, remote=True, branch="feature")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=head,
            pr_checks=[{"bucket": "fail", "name": "Python", "workflow": "Checks"}],
            runs=[
                {
                    "databaseId": 104,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "failure",
                    "headSha": head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/104",
                }
            ],
            jobs=[
                {
                    "databaseId": 204,
                    "name": "Python Checks (3.12)",
                    "status": "completed",
                    "conclusion": "failure",
                    "url": "https://github.com/alik-git/qstatus/actions/runs/104/job/204",
                }
            ],
            log_failed="line 1\nline 2\nline 3\nline 4\n",
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo, log_tail=2)

    assert snapshot.summary is not None
    assert snapshot.summary.ci_state == "failure"
    assert snapshot.jobs[0].name == "Python Checks (3.12)"
    assert snapshot.jobs[0].bucket == "fail"
    assert snapshot.log_tails[0].lines == ["line 3", "line 4"]
    assert snapshot.log_tails[0].capped is True


def test_ci_log_tail_failure_is_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Log-tail failures should not fail the whole snapshot."""
    repo = _repo(tmp_path, remote=True, branch="feature")
    head = _git(repo, "rev-parse", "HEAD")

    monkeypatch.setattr(
        qstatus.ci_snapshot,
        "run_command",
        _fake_gh(
            head=head,
            pr_head=head,
            pr_checks=[{"bucket": "fail", "name": "Python", "workflow": "Checks"}],
            runs=[
                {
                    "databaseId": 105,
                    "workflowName": "Checks",
                    "status": "completed",
                    "conclusion": "failure",
                    "headSha": head,
                    "url": "https://github.com/alik-git/qstatus/actions/runs/105",
                }
            ],
            jobs=[],
            log_failed=None,
        ),
    )

    snapshot = qstatus.ci_snapshot.collect_ci_snapshot(repo, log_tail=10)

    assert snapshot.currentness.state == "current"
    assert snapshot.log_tails[0].status == "unavailable"
    assert snapshot.log_tails[0].reason is not None


def test_cli_ci_missing_gh_is_structured_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing gh should produce unavailable CI JSON, not a traceback."""
    repo = _repo(tmp_path, remote=True, branch="feature")

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        del timeout_s
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=None,
            stdout="",
            stderr="missing gh",
            unavailable=True,
        )

    monkeypatch.setattr(qstatus.ci_snapshot, "run_command", fake_run_command)

    assert main(["ci", "--cwd", str(repo), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["github"]["status"] == "unavailable"
    assert payload["github"]["error"] == "gh is not installed"


def _repo(tmp_path: Path, *, remote: bool = False, branch: str = "main") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README.md").write_text("# Test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", branch)
    if remote:
        _git(repo, "remote", "add", "origin", "git@github.com:alik-git/qstatus.git")
    return repo


def _git(repo: Path, *args: str) -> str:
    result = run_command(["git", *args], cwd=repo, timeout_s=10.0)
    assert result.ok, result.stderr or result.stdout
    return result.stdout.strip()


def _fake_gh(
    *,
    head: str,
    pr_head: str | None,
    pr_checks: list[dict[str, object]],
    runs: list[dict[str, object]],
    jobs: list[dict[str, object]] | None = None,
    log_failed: str | None = "",
) -> Callable[..., CommandResult]:
    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        del timeout_s
        if args[:3] == ["gh", "auth", "status"]:
            return _ok(args, cwd, "")
        if args[:3] == ["gh", "pr", "view"]:
            if pr_head is None:
                return _fail(args, cwd, "no pull requests found")
            return _ok(
                args,
                cwd,
                json.dumps(
                    {
                        "number": 2,
                        "title": "Test PR",
                        "url": "https://github.com/alik-git/qstatus/pull/2",
                        "state": "OPEN",
                        "isDraft": False,
                        "baseRefName": "main",
                        "baseRefOid": "b" * 40,
                        "headRefName": "feature",
                        "headRefOid": pr_head,
                        "reviewDecision": "APPROVED",
                    }
                ),
            )
        if args[:3] == ["gh", "pr", "status"]:
            return _ok(args, cwd, json.dumps({"createdBy": [], "needsReview": []}))
        if args[:3] == ["gh", "pr", "list"]:
            return _ok(args, cwd, json.dumps([]))
        if args[:3] == ["gh", "pr", "checks"]:
            return _ok(args, cwd, json.dumps(pr_checks))
        if args[:3] == ["gh", "run", "list"]:
            return _ok(args, cwd, json.dumps(runs))
        if args[:3] == ["gh", "run", "view"] and "--json" in args:
            return _ok(
                args,
                cwd,
                json.dumps(
                    {
                        "databaseId": runs[0].get("databaseId") if runs else 0,
                        "jobs": jobs or [],
                    }
                ),
            )
        if args[:3] == ["gh", "run", "view"] and "--log-failed" in args:
            if log_failed is None:
                return _fail(args, cwd, "log unavailable")
            return _ok(args, cwd, log_failed)
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return _ok(args, cwd, head)
        raise AssertionError(args)

    return fake_run_command


def _ok(args: list[str], cwd: Path, stdout: str) -> CommandResult:
    return CommandResult(
        args=tuple(args),
        cwd=cwd,
        exit_code=0,
        stdout=stdout,
        stderr="",
    )


def _fail(args: list[str], cwd: Path, stderr: str) -> CommandResult:
    return CommandResult(
        args=tuple(args),
        cwd=cwd,
        exit_code=1,
        stdout="",
        stderr=stderr,
    )
