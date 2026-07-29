"""Bounded multi-repository snapshot collection."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quick_status.git_snapshot import RepoSnapshotError, collect_repo_snapshot
from quick_status.github import collect_github_context, enrich_repo_snapshot
from quick_status.github_client import GitHubMemoryCache

if TYPE_CHECKING:
    from quick_status.models import RepoSnapshot

BATCH_SCHEMA_VERSION = "quick_status_repo_batch_v1"


@dataclass(frozen=True, slots=True)
class BatchItem:
    """One repository result in a deterministic batch."""

    path: str
    status: str
    duration_ms: float
    snapshot: RepoSnapshot | None = None
    error: str | None = None

    def to_dict(self, *, include_commands: bool) -> dict[str, object]:
        """Convert one batch item to stable JSON."""
        return {
            "path": self.path,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 3),
            "snapshot": (
                self.snapshot.to_dict(include_commands=include_commands)
                if self.snapshot is not None
                else None
            ),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class BatchSnapshot:
    """A deterministic collection of explicit repository snapshots."""

    schema_version: str
    items: list[BatchItem]

    def to_dict(self, *, include_commands: bool) -> dict[str, object]:
        """Convert the batch to stable JSON."""
        return {
            "schema_version": self.schema_version,
            "items": [
                item.to_dict(include_commands=include_commands) for item in self.items
            ],
        }


def collect_repo_batch(
    paths: list[Path],
    *,
    workers: int = 4,
    include_github: bool = False,
    include_release: bool = False,
    include_commands: bool = False,
    include_details: bool = False,
    max_age_s: float = 0.0,
    timeout_s: float = 10.0,
) -> BatchSnapshot:
    """Collect explicit repositories concurrently while preserving input order."""
    resolved = [path.expanduser().resolve() for path in paths]
    if not resolved:
        return BatchSnapshot(schema_version=BATCH_SCHEMA_VERSION, items=[])
    bounded_workers = max(1, min(workers, len(resolved)))
    indexed: dict[int, BatchItem] = {}
    memory_cache = GitHubMemoryCache()
    with ThreadPoolExecutor(max_workers=bounded_workers) as executor:
        futures = {
            executor.submit(
                _collect_one,
                path,
                include_github=include_github,
                include_release=include_release,
                include_commands=include_commands,
                include_details=include_details,
                max_age_s=max_age_s,
                timeout_s=timeout_s,
                memory_cache=memory_cache,
            ): index
            for index, path in enumerate(resolved)
        }
        for future in as_completed(futures):
            indexed[futures[future]] = future.result()
    return BatchSnapshot(
        schema_version=BATCH_SCHEMA_VERSION,
        items=[indexed[index] for index in range(len(resolved))],
    )


def discover_workset_repositories(root: Path) -> list[Path]:
    """Return immediate Git worktree children from an explicit workset directory."""
    resolved = root.expanduser().resolve()
    if not resolved.exists():
        msg = f"workset directory does not exist: {resolved}"
        raise ValueError(msg)
    if not resolved.is_dir():
        msg = f"not a workset directory: {resolved}"
        raise ValueError(msg)
    repositories = [
        child
        for child in resolved.iterdir()
        if child.is_dir() and (child / ".git").exists()
    ]
    return sorted(repositories, key=lambda path: path.name)


def _collect_one(
    path: Path,
    *,
    include_github: bool,
    include_release: bool,
    include_commands: bool,
    include_details: bool,
    max_age_s: float,
    timeout_s: float,
    memory_cache: GitHubMemoryCache,
) -> BatchItem:
    started = time.perf_counter()
    try:
        snapshot = collect_repo_snapshot(
            path,
            include_github=include_github,
            include_commands=include_commands,
            include_details=include_details,
            include_worktrees=include_details,
        )
        if include_github:
            github, github_commands = collect_github_context(
                repo=snapshot.repo.github_repo,
                branch=snapshot.branch,
                root=Path(snapshot.repo.root),
                include_commands=include_commands,
                include_release=include_release,
                max_age_s=max_age_s,
                timeout_s=timeout_s,
                memory_cache=memory_cache,
            )
            snapshot = enrich_repo_snapshot(snapshot, github, github_commands)
    except RepoSnapshotError as exc:
        return BatchItem(
            path=str(path),
            status="error",
            duration_ms=(time.perf_counter() - started) * 1000,
            error=str(exc),
        )
    return BatchItem(
        path=str(path),
        status="ok",
        duration_ms=(time.perf_counter() - started) * 1000,
        snapshot=snapshot,
    )
