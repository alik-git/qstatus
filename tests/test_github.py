"""Tests for shared GitHub evidence collection."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quick_status.commands import CommandResult
from quick_status.github import (
    collect_github_context,
    summarize_workflow_runs,
)
from quick_status.models import BranchState

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_summarize_workflow_runs_success_state() -> None:
    """Summarize completed workflow runs."""
    summary = summarize_workflow_runs(
        [
            {"status": "completed", "conclusion": "success"},
            {"status": "completed", "conclusion": "success"},
        ],
        head_sha="abc",
    )

    assert summary.state == "success"
    assert summary.total == 2
    assert summary.success == 2


def test_collect_github_context_uses_one_pr_rollup_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collect a PR and checks without auth, view, status, or checks queries."""
    branch = _branch()
    calls: list[list[str]] = []

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return one PR with an inline check rollup."""
        del timeout_s
        calls.append(args)
        return _ok(
            args,
            cwd,
            [
                {
                    "number": 12,
                    "title": "Fast GitHub evidence",
                    "url": "https://github.com/alik-git/quick-status/pull/12",
                    "state": "OPEN",
                    "isDraft": False,
                    "baseRefName": "main",
                    "baseRefOid": "b" * 40,
                    "headRefName": "feature",
                    "headRefOid": "a" * 40,
                    "reviewDecision": "APPROVED",
                    "statusCheckRollup": [
                        {
                            "name": "Tests",
                            "status": "COMPLETED",
                            "conclusion": "SUCCESS",
                        }
                    ],
                }
            ],
        )

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)

    context, commands = collect_github_context(
        repo="alik-git/quick-status",
        branch=branch,
        root=tmp_path,
        include_commands=True,
    )

    assert context.status == "available"
    assert context.pr_state == "open"
    assert context.pull_request is not None
    assert context.pull_request.head_oid == "a" * 40
    assert context.checks is not None
    assert context.checks.state == "success"
    assert context.checks.head_sha == "a" * 40
    assert context.release is None
    assert len(commands) == 1
    assert len(calls) == 1
    assert calls[0][:3] == ["gh", "pr", "list"]


def test_collect_github_context_no_pr_queries_exact_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A no-PR branch should query workflow runs for the exact local OID."""
    branch = _branch()
    calls: list[list[str]] = []

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return no PR and one successful exact-commit run."""
        del timeout_s
        calls.append(args)
        if args[:3] == ["gh", "pr", "list"]:
            return _ok(args, cwd, [])
        if args[:3] == ["gh", "run", "list"]:
            return _ok(
                args,
                cwd,
                [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "headSha": branch.oid,
                    }
                ],
            )
        raise AssertionError(args)

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)

    context, _ = collect_github_context(
        repo="alik-git/quick-status",
        branch=branch,
        root=tmp_path,
    )

    assert context.pr_state == "none"
    assert context.checks is not None
    assert context.checks.state == "success"
    assert len(calls) == 2
    assert "--commit" in calls[1]
    assert "--branch" not in calls[1]


def test_collect_github_context_closed_pr_uses_current_commit_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale closed PR rollup must not describe the current local commit."""
    branch = _branch()
    calls: list[list[str]] = []

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return a failed old PR and a successful run for the current commit."""
        del timeout_s
        calls.append(args)
        if args[:3] == ["gh", "pr", "list"]:
            return _ok(
                args,
                cwd,
                [
                    {
                        "number": 11,
                        "title": "Old pull request",
                        "url": "https://github.com/alik-git/quick-status/pull/11",
                        "state": "CLOSED",
                        "isDraft": False,
                        "headRefName": "feature",
                        "headRefOid": "0" * 40,
                        "statusCheckRollup": [
                            {
                                "name": "Tests",
                                "status": "COMPLETED",
                                "conclusion": "FAILURE",
                            }
                        ],
                    }
                ],
            )
        if args[:3] == ["gh", "run", "list"]:
            return _ok(
                args,
                cwd,
                [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "headSha": branch.oid,
                    }
                ],
            )
        raise AssertionError(args)

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)

    context, _ = collect_github_context(
        repo="alik-git/quick-status",
        branch=branch,
        root=tmp_path,
    )

    assert context.pr_state == "closed"
    assert context.checks is not None
    assert context.checks.state == "success"
    assert context.checks.head_sha == branch.oid
    assert len(calls) == 2
    assert "--commit" in calls[1]


def test_collect_github_context_preserves_query_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient PR query failure must not become a factual no-PR result."""

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return a rate-limit error."""
        del timeout_s
        return _fail(args, cwd, "API rate limit exceeded")

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)

    context, _ = collect_github_context(
        repo="alik-git/quick-status",
        branch=_branch(),
        root=tmp_path,
    )

    assert context.status == "error"
    assert context.pr_state == "unknown"
    assert context.pull_request is None
    assert context.error is not None
    assert "rate limit" in context.error


def test_collect_github_context_reports_missing_gh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing GitHub CLI should be structured unavailable data."""

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return a missing executable result."""
        del timeout_s
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=None,
            stdout="",
            stderr="missing gh",
            unavailable=True,
        )

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)

    context, _ = collect_github_context(
        repo="alik-git/quick-status",
        branch=_branch(),
        root=tmp_path,
    )

    assert context.status == "unavailable"
    assert context.pr_state == "unknown"
    assert context.error is not None
    assert "gh is not installed" in context.error


def _branch() -> BranchState:
    return BranchState(
        head="feature",
        oid="abcdef1234567890",
        short_oid="abcdef1",
        upstream="origin/feature",
        ahead=0,
        behind=0,
        sync_state="synced",
    )


def _ok(args: list[str], cwd: Path, payload: object) -> CommandResult:
    return CommandResult(
        args=tuple(args),
        cwd=cwd,
        exit_code=0,
        stdout=json.dumps(payload),
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
