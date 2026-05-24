"""Command-line entry point for qstatus."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from qstatus import __version__
from qstatus.git_snapshot import RepoSnapshotError, collect_repo_snapshot
from qstatus.github import collect_github_context
from qstatus.models import RepoSummary
from qstatus.render import (
    render_human,
    render_human_github_lines,
    render_human_local_lines,
    render_human_verbose_lines,
    render_json,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


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
        "--plain",
        action="store_true",
        help="disable ANSI color in human-readable output",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="control ANSI color in human-readable output",
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

    color = _should_colorize(
        args.color,
        plain=args.plain,
        stream=sys.stdout,
    )
    if args.github and not args.json_output:
        _print_lines(render_human_local_lines(snapshot, color=color), flush=True)

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
    elif args.github:
        _print_lines(render_human_github_lines(snapshot, color=color))
        if args.verbose:
            _print_lines(render_human_verbose_lines(snapshot, color=color))
    else:
        print(render_human(snapshot, verbose=args.verbose, color=color))
    return 0


def _print_lines(lines: list[str], *, flush: bool = False) -> None:
    """Print pre-rendered human lines, optionally flushing for progressive output."""
    if not lines:
        return
    print("\n".join(lines), flush=flush)


def _should_colorize(
    color_mode: str,
    *,
    plain: bool,
    stream: object,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Return true when human output should include ANSI color."""
    if plain or color_mode == "never":
        return False
    if color_mode == "always":
        return True
    actual_env = os.environ if env is None else env
    if "NO_COLOR" in actual_env or actual_env.get("TERM") == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


if __name__ == "__main__":
    sys.exit(main())
