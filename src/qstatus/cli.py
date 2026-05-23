"""Command-line entry point for qstatus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from qstatus import __version__
from qstatus.git_snapshot import RepoSnapshotError, collect_repo_snapshot
from qstatus.github import collect_github_context
from qstatus.models import RepoSummary
from qstatus.render import render_human, render_json


def build_repo_parser(prog: str = "qstatus") -> argparse.ArgumentParser:
    """Build the qstatus repo command-line parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print a quick local repository status snapshot.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="emit stable JSON instead of human-readable text",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="include read-only GitHub PR, CI, and release context via gh",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="repo directory to inspect",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="include extra evidence such as command records",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the qstatus command-line interface."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list == ["--version"]:
        print(f"qstatus {__version__}")
        return 0

    prog = "qstatus"
    if args_list[:1] == ["repo"]:
        prog = "qstatus repo"
        args_list = args_list[1:]
    parser = build_repo_parser(prog)
    args = parser.parse_args(args_list)

    cwd = args.cwd.expanduser().resolve()
    try:
        snapshot = collect_repo_snapshot(
            cwd,
            include_github=args.github,
            include_commands=args.verbose,
        )
    except RepoSnapshotError as exc:
        if args.json_output:
            print(
                json.dumps(
                    {"error": str(exc), "schema_version": "qstatus_error_v1"},
                    sort_keys=True,
                ),
            )
        else:
            print(f"qstatus: {exc}", file=sys.stderr)
        return 2

    if args.github:
        github, github_commands = collect_github_context(
            repo=snapshot.repo.github_repo,
            branch=snapshot.branch,
            root=Path(snapshot.repo.root),
            include_commands=args.verbose,
        )
        commands = [*snapshot.commands, *github_commands]
        snapshot = replace(
            snapshot,
            github=github,
            commands=commands,
            summary=RepoSummary(
                sync_state=snapshot.summary.sync_state,
                worktree_state=snapshot.summary.worktree_state,
                pr_state=github.pr_state,
                remote_check_state=github.checks.state if github.checks else "unknown",
            ),
        )

    if args.json_output:
        print(render_json(snapshot, verbose=args.verbose))
    else:
        print(render_human(snapshot, verbose=args.verbose))
    return 0


if __name__ == "__main__":
    sys.exit(main())
