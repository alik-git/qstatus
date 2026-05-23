"""Tests for GitHub context summarization."""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

from qstatus.commands import CommandResult
from qstatus.github import (
    collect_github_context,
    summarize_pr_checks,
    summarize_workflow_runs,
)
from qstatus.models import BranchState

if TYPE_CHECKING:
    import pytest


def test_summarize_pr_checks_mixed_state() -> None:
    """Summarize mixed PR checks without claiming readiness."""
    summary = summarize_pr_checks(
        [
            {"bucket": "pass"},
            {"bucket": "fail"},
            {"bucket": "pending"},
            {"bucket": "skipping"},
        ],
        head_sha="abc",
    )

    assert summary.state == "mixed"
    assert summary.total == 4
    assert summary.success == 1
    assert summary.failure == 1
    assert summary.pending == 1
    assert summary.skipped == 1


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


def test_collect_github_context_with_fake_gh(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collect GitHub context through fake gh JSON responses."""
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n')
    branch = BranchState(
        head="feature",
        oid="abcdef1234567890",
        short_oid="abcdef1",
        upstream="origin/feature",
        ahead=0,
        behind=0,
        sync_state="synced",
    )

    def fake_run_command(
        args: list[str],
        *,
        cwd: pathlib.Path,
        timeout_s: float,
    ) -> CommandResult:
        del cwd, timeout_s
        if args[:3] == ["gh", "auth", "status"]:
            return _ok(args, "{}")
        if args[:3] == ["gh", "pr", "view"]:
            return _ok(
                args,
                json.dumps(
                    {
                        "number": 12,
                        "title": "Add repo command",
                        "url": "https://github.com/alik-git/qstatus/pull/12",
                        "state": "OPEN",
                        "isDraft": False,
                        "baseRefName": "main",
                        "headRefName": "feature",
                        "reviewDecision": "APPROVED",
                    },
                ),
            )
        if args[:3] == ["gh", "pr", "checks"]:
            return _ok(args, json.dumps([{"bucket": "pass"}, {"bucket": "pass"}]))
        if args[:3] == ["gh", "release", "view"]:
            return _ok(
                args,
                json.dumps(
                    {
                        "tagName": "v0.2.0",
                        "url": "https://github.com/alik-git/qstatus/releases/tag/v0.2.0",
                    },
                ),
            )
        raise AssertionError(args)

    monkeypatch.setattr("qstatus.github.run_command", fake_run_command)

    context, commands = collect_github_context(
        repo="alik-git/qstatus",
        branch=branch,
        root=tmp_path,
        include_commands=True,
    )

    assert context.status == "available"
    assert context.pr_state == "open"
    assert context.pull_request is not None
    assert context.pull_request.number == 12
    assert context.checks is not None
    assert context.checks.state == "success"
    assert context.release is not None
    assert context.release.exists is True
    assert len(commands) == 4


def test_collect_github_context_falls_back_to_pr_status(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Find a branch PR through the structured status fallback."""
    branch = BranchState(
        head="feature",
        oid="abcdef1234567890",
        short_oid="abcdef1",
        upstream="origin/feature",
        ahead=0,
        behind=0,
        sync_state="synced",
    )

    def fake_run_command(
        args: list[str],
        *,
        cwd: pathlib.Path,
        timeout_s: float,
    ) -> CommandResult:
        del cwd, timeout_s
        if args[:3] == ["gh", "auth", "status"]:
            return _ok(args, "{}")
        if args[:3] == ["gh", "pr", "view"]:
            return _fail(args, "no pull requests found")
        if args[:3] == ["gh", "pr", "status"]:
            return _ok(
                args,
                json.dumps(
                    {
                        "createdBy": [
                            {
                                "number": 7,
                                "title": "Fallback PR",
                                "url": "https://github.com/alik-git/qstatus/pull/7",
                                "state": "OPEN",
                                "isDraft": True,
                                "baseRefName": "main",
                                "headRefName": "feature",
                                "reviewDecision": "",
                            },
                        ],
                        "needsReview": [],
                    }
                ),
            )
        if args[:3] == ["gh", "pr", "checks"]:
            return _ok(args, json.dumps([]))
        if args[:3] == ["gh", "release", "view"]:
            return _fail(args, "release not found")
        raise AssertionError(args)

    monkeypatch.setattr("qstatus.github.run_command", fake_run_command)

    context, _commands = collect_github_context(
        repo="alik-git/qstatus",
        branch=branch,
        root=tmp_path,
    )

    assert context.pr_state == "draft"
    assert context.pull_request is not None
    assert context.pull_request.number == 7


def test_collect_github_context_falls_back_to_pr_list(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fall back to a branch PR list when status has no branch match."""
    branch = BranchState(
        head="feature",
        oid="abcdef1234567890",
        short_oid="abcdef1",
        upstream="origin/feature",
        ahead=0,
        behind=0,
        sync_state="synced",
    )

    def fake_run_command(
        args: list[str],
        *,
        cwd: pathlib.Path,
        timeout_s: float,
    ) -> CommandResult:
        del cwd, timeout_s
        if args[:3] == ["gh", "auth", "status"]:
            return _ok(args, "{}")
        if args[:3] == ["gh", "pr", "view"]:
            return _fail(args, "no pull requests found")
        if args[:3] == ["gh", "pr", "status"]:
            return _ok(args, json.dumps({"createdBy": [], "needsReview": []}))
        if args[:3] == ["gh", "pr", "list"]:
            return _ok(
                args,
                json.dumps(
                    [
                        {
                            "number": 8,
                            "title": "List fallback PR",
                            "url": "https://github.com/alik-git/qstatus/pull/8",
                            "state": "OPEN",
                            "isDraft": False,
                            "baseRefName": "main",
                            "headRefName": "feature",
                            "reviewDecision": "",
                        },
                    ]
                ),
            )
        if args[:3] == ["gh", "pr", "checks"]:
            return _ok(args, json.dumps([]))
        if args[:3] == ["gh", "release", "view"]:
            return _fail(args, "release not found")
        raise AssertionError(args)

    monkeypatch.setattr("qstatus.github.run_command", fake_run_command)

    context, _commands = collect_github_context(
        repo="alik-git/qstatus",
        branch=branch,
        root=tmp_path,
    )

    assert context.pr_state == "open"
    assert context.pull_request is not None
    assert context.pull_request.number == 8


def test_collect_github_context_reports_missing_gh(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report unavailable GitHub context when gh cannot run."""
    branch = BranchState(
        head="feature",
        oid="abcdef1234567890",
        short_oid="abcdef1",
        upstream="origin/feature",
        ahead=0,
        behind=0,
        sync_state="synced",
    )

    def fake_run_command(
        args: list[str],
        *,
        cwd: pathlib.Path,
        timeout_s: float,
    ) -> CommandResult:
        del cwd, timeout_s
        return CommandResult(
            args=tuple(args),
            cwd=tmp_path,
            exit_code=None,
            stdout="",
            stderr="missing gh",
            unavailable=True,
        )

    monkeypatch.setattr("qstatus.github.run_command", fake_run_command)

    context, _commands = collect_github_context(
        repo="alik-git/qstatus",
        branch=branch,
        root=tmp_path,
    )

    assert context.status == "unavailable"
    assert context.error == "gh is not installed"


def _ok(args: list[str], stdout: str) -> CommandResult:
    return CommandResult(
        args=tuple(args),
        cwd=pathlib.Path.cwd(),
        exit_code=0,
        stdout=stdout,
        stderr="",
    )


def _fail(args: list[str], stderr: str) -> CommandResult:
    return CommandResult(
        args=tuple(args),
        cwd=pathlib.Path.cwd(),
        exit_code=1,
        stdout="",
        stderr=stderr,
    )
