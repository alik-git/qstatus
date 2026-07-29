"""Tests for explicit GitHub response caching and deadlines."""

from __future__ import annotations

import json
import stat
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from quick_status.commands import CommandResult
from quick_status.github_client import GitHubClient, GitHubMemoryCache

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_explicit_cache_reuses_successful_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A positive max age should expose and reuse successful JSON evidence."""
    calls = 0

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return one live successful query."""
        nonlocal calls
        del timeout_s
        calls += 1
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=0,
            stdout=json.dumps([]),
            stderr="",
        )

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)
    cache_dir = tmp_path / "cache"
    args = ["pr", "list", "--repo", "owner/repo", "--json", "number"]

    first = GitHubClient(tmp_path, max_age_s=5, cache_dir=cache_dir)
    assert first.json_list(args).ok
    assert first.provenance().source == "live"

    second = GitHubClient(tmp_path, max_age_s=5, cache_dir=cache_dir)
    assert second.json_list(args).ok
    provenance = second.provenance()

    assert calls == 1
    assert provenance.source == "cache"
    assert provenance.age_seconds is not None
    assert provenance.collected_at is not None
    cache_file = next((cache_dir / "github").iterdir())
    assert stat.S_IMODE(cache_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache_file.parent.stat().st_mode) == 0o700


def test_failed_queries_are_not_cached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient failures must be retried live rather than cached."""
    calls = 0

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return a transient error."""
        nonlocal calls
        del timeout_s
        calls += 1
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=1,
            stdout="",
            stderr="temporary failure",
        )

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)
    cache_dir = tmp_path / "cache"
    args = ["pr", "list", "--repo", "owner/repo", "--json", "number"]

    assert (
        not GitHubClient(
            tmp_path,
            max_age_s=5,
            cache_dir=cache_dir,
        )
        .json_list(args)
        .ok
    )
    assert (
        not GitHubClient(
            tmp_path,
            max_age_s=5,
            cache_dir=cache_dir,
        )
        .json_list(args)
        .ok
    )

    assert calls == 2


def test_batch_memory_cache_single_flights_identical_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent clients should execute one exact live query only once."""
    calls = 0

    def fake_run_command(
        args: list[str],
        *,
        cwd: Path,
        timeout_s: float,
    ) -> CommandResult:
        """Return a deliberately overlapping live response."""
        nonlocal calls
        del timeout_s
        calls += 1
        time.sleep(0.05)
        return CommandResult(
            args=tuple(args),
            cwd=cwd,
            exit_code=0,
            stdout=json.dumps([]),
            stderr="",
        )

    monkeypatch.setattr("quick_status.github_client.run_command", fake_run_command)
    memory_cache = GitHubMemoryCache()
    args = ["pr", "list", "--repo", "owner/repo", "--json", "number"]
    clients = [
        GitHubClient(tmp_path, memory_cache=memory_cache),
        GitHubClient(tmp_path, memory_cache=memory_cache),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda client: client.json_list(args), clients))

    assert all(result.ok for result in results)
    assert calls == 1


def test_global_deadline_stops_new_queries(tmp_path: Path) -> None:
    """An exhausted collection deadline should not spawn another process."""
    client = GitHubClient(tmp_path, timeout_s=1)
    client.deadline = time.monotonic() - 1

    result = client.json_list(
        ["pr", "list", "--repo", "owner/repo", "--json", "number"]
    )

    assert not result.ok
    assert result.command.timed_out is True
    assert result.error == "GitHub collection deadline exceeded"
