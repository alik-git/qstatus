"""Human and JSON rendering for multi-repository snapshots."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from quick_status import formatting as fmt

if TYPE_CHECKING:
    from quick_status.batch import BatchSnapshot


def render_batch_json(snapshot: BatchSnapshot, *, verbose: bool = False) -> str:
    """Render a batch snapshot as stable JSON."""
    return json.dumps(
        snapshot.to_dict(include_commands=verbose),
        indent=2,
        sort_keys=True,
    )


def render_batch_human(
    snapshot: BatchSnapshot,
    *,
    color: bool = False,
) -> str:
    """Render one deterministic compact line per repository."""
    lines: list[str] = []
    for item in snapshot.items:
        if item.snapshot is None:
            lines.append(
                f"{fmt.label('REPO_ERROR', color)} {fmt.variable(item.path, color)} "
                f"{item.error or 'unknown error'}"
            )
            continue
        repo = item.snapshot
        lines.append(
            f"{fmt.label('REPO', color)} {fmt.name(repo.repo.name, color)} "
            f"branch={fmt.name(repo.branch.head, color)} "
            f"state={fmt.state(repo.changes.worktree_state, color)} "
            f"sync={fmt.state(repo.branch.sync_state, color)} "
            f"sync_source={repo.branch.sync_source} "
            f"pr={fmt.state(repo.summary.pr_state, color)} "
            f"ci={fmt.state(repo.summary.remote_check_state, color)} "
            f"duration_ms={item.duration_ms:.1f} "
            f"path={fmt.variable(repo.repo.root, color)}"
        )
    return "\n".join(lines)
