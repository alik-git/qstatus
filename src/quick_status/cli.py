"""Command-line entry point for quick-status."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from quick_status import __version__

if TYPE_CHECKING:
    from collections.abc import Mapping


_REPO_HELP_EPILOG = """\
Commands:
  quick-status [PATH]       local Git/repo status
  quick-status repos ...    concurrent explicit multi-repo status
  quick-status workset DIR  status for immediate repos in a workset
  quick-status env          Python, conda, venv, veneer, and tool status
  quick-status ci           detailed read-only GitHub CI status
  quick-status reminders    opt-in shell reminders for habitual commands

Examples:
  quick-status repo --worktrees
  quick-status repo --stashes --stash-limit 5
  quick-status repo --github
  quick-status repos repo-a repo-b --github
  quick-status workset ~/Projects/worksets/my-task
  quick-status env --show-all
  quick-status ci --log-tail 40
  eval "$(quick-status reminders init bash)"

Run `quick-status env --help`, `quick-status ci --help`, or
`quick-status reminders --help` for command-specific options.
"""


_ENV_HELP_EPILOG = """\
Examples:
  quick-status env
  quick-status env --compact
  quick-status env --show-tools --show-hints
  quick-status env --json
"""


_CI_HELP_EPILOG = """\
Examples:
  quick-status ci
  quick-status ci --json
  quick-status ci --log-tail 40
"""


_REMINDERS_HELP_EPILOG = """\
Examples:
  quick-status reminders init bash
  quick-status reminders init bash --context codex
  eval "$(quick-status reminders init bash)"
"""


def build_repo_parser(prog: str = "quick-status") -> argparse.ArgumentParser:
    """Build the quick-status repo command-line parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print a quick local repository status snapshot.",
        epilog=_REPO_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "repo_path",
        type=Path,
        nargs="?",
        help="repo directory to inspect",
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
        help="include read-only GitHub PR and CI context via gh",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="also query the project-version GitHub release",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="reuse successful remote JSON responses up to this age",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="overall GitHub collection deadline",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="repo directory to inspect",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="include extra evidence such as command records",
    )
    parser.add_argument(
        "--non-compact",
        action="store_true",
        help="use the sectioned human-readable repo summary",
    )
    parser.add_argument(
        "--worktrees",
        action="store_true",
        help="show linked worktrees for this repo family",
    )
    parser.add_argument(
        "--stashes",
        action="store_true",
        help="show bounded stash details for this repo family",
    )
    parser.add_argument(
        "--stash-limit",
        type=int,
        default=5,
        help="maximum stash entries to show with --stashes",
    )
    return parser


def build_env_parser(prog: str = "quick-status env") -> argparse.ArgumentParser:
    """Build the quick-status env command-line parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print a quick Python and project environment snapshot.",
        epilog=_ENV_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="project directory to inspect",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="include extra evidence such as safe env vars and command records",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="use the original one-line human-readable env summary",
    )
    parser.add_argument(
        "--abs-paths",
        action="store_true",
        help="print absolute paths in human-readable output",
    )
    parser.add_argument(
        "--show-home",
        action="store_true",
        help="show the home-directory path used for ~ path compaction",
    )
    parser.add_argument(
        "--show-tools",
        action="store_true",
        help="show optional tool executable paths in human-readable output",
    )
    parser.add_argument(
        "--show-hints",
        action="store_true",
        help="show command-shaped execution hints in human-readable output",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="show all optional human-readable env sections",
    )
    return parser


def build_batch_parser(
    prog: str,
    *,
    workset: bool,
) -> argparse.ArgumentParser:
    """Build the explicit multi-repository command parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Inspect immediate repositories in one workset."
            if workset
            else "Inspect explicit repositories concurrently."
        ),
    )
    parser.add_argument(
        "paths",
        type=Path,
        nargs=1 if workset else "+",
        help="workset directory" if workset else "repo directories to inspect",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="emit stable JSON instead of human-readable text",
    )
    parser.add_argument("--plain", action="store_true", help="disable ANSI color")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="control ANSI color in human-readable output",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="include read-only GitHub PR and CI context",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="also query each project-version GitHub release",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="reuse successful remote JSON responses up to this age",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="overall GitHub deadline per repository",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="maximum repositories inspected concurrently",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="include command records in JSON",
    )
    return parser


def build_ci_parser(prog: str = "quick-status ci") -> argparse.ArgumentParser:
    """Build the quick-status ci command-line parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print a read-only GitHub CI status snapshot.",
        epilog=_CI_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--log-tail",
        type=int,
        nargs="?",
        const=40,
        default=None,
        help="print the last N non-empty lines from failed GitHub Actions logs",
    )
    parser.add_argument(
        "--max-age",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="reuse successful remote JSON responses up to this age",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="overall GitHub collection deadline",
    )
    return parser


def build_reminders_parser(
    prog: str = "quick-status reminders",
) -> argparse.ArgumentParser:
    """Build the quick-status reminders command-line parser."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Print opt-in shell integration for quick-status reminders.",
        epilog=_REMINDERS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    init_parser = subparsers.add_parser(
        "init",
        help="print shell integration source",
    )
    init_parser.add_argument(
        "shell",
        choices=("bash",),
        help="shell integration to print",
    )
    init_parser.add_argument(
        "--context",
        choices=("interactive", "codex"),
        default="interactive",
        help="reminder policy context to render",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the quick-status command-line interface."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list == ["--version"]:
        print(f"quick-status {__version__}")
        return 0

    prog = "quick-status"
    command = "repo"
    if args_list[:1] == ["repo"]:
        prog = "quick-status repo"
        args_list = args_list[1:]
    elif args_list[:1] == ["env"]:
        prog = "quick-status env"
        command = "env"
        args_list = args_list[1:]
    elif args_list[:1] == ["repos"]:
        prog = "quick-status repos"
        command = "repos"
        args_list = args_list[1:]
    elif args_list[:1] == ["workset"]:
        prog = "quick-status workset"
        command = "workset"
        args_list = args_list[1:]
    elif args_list[:1] == ["ci"]:
        prog = "quick-status ci"
        command = "ci"
        args_list = args_list[1:]
    elif args_list[:1] == ["reminders"]:
        prog = "quick-status reminders"
        command = "reminders"
        args_list = args_list[1:]

    if command == "env":
        parser = build_env_parser(prog)
    elif command in {"repos", "workset"}:
        parser = build_batch_parser(prog, workset=command == "workset")
    elif command == "ci":
        parser = build_ci_parser(prog)
    elif command == "reminders":
        parser = build_reminders_parser(prog)
    else:
        parser = build_repo_parser(prog)
    args = parser.parse_args(args_list)

    if command == "reminders":
        from quick_status.reminders import render_reminders_init

        print(render_reminders_init(args.shell, context=args.context), end="")
        return 0
    if command in {"repos", "workset"}:
        return _run_batch(args, parser, workset=command == "workset")

    repo_path = getattr(args, "repo_path", None)
    if repo_path is not None and args.cwd is not None:
        parser.error("repository path and --cwd cannot be used together")
    cwd_arg = repo_path or args.cwd or Path.cwd()
    cwd = cwd_arg.expanduser().resolve()
    if command == "ci":
        from quick_status.ci_render import render_ci_human, render_ci_json
        from quick_status.ci_snapshot import collect_ci_snapshot, validate_log_tail
        from quick_status.git_snapshot import RepoSnapshotError

        try:
            log_tail = validate_log_tail(args.log_tail)
        except ValueError as exc:
            parser.error(str(exc))
        _validate_remote_options(parser, max_age=args.max_age, timeout=args.timeout)
        try:
            ci_snapshot = collect_ci_snapshot(
                cwd,
                include_commands=args.verbose,
                log_tail=log_tail,
                max_age_s=args.max_age,
                timeout_s=args.timeout,
            )
        except RepoSnapshotError as exc:
            if args.json_output:
                print(
                    json.dumps(
                        {"error": str(exc), "schema_version": "quick_status_error_v1"},
                        sort_keys=True,
                    ),
                )
            else:
                print(f"quick-status: {exc}", file=sys.stderr)
            return 2
        color = _should_colorize(
            args.color,
            plain=args.plain,
            stream=sys.stdout,
        )
        if args.json_output:
            print(render_ci_json(ci_snapshot, verbose=args.verbose))
        else:
            print(render_ci_human(ci_snapshot, verbose=args.verbose, color=color))
        return 0

    if command == "env":
        from quick_status.env_render import render_env_human, render_env_json
        from quick_status.env_snapshot import collect_env_snapshot

        env_snapshot = collect_env_snapshot(
            cwd,
            include_commands=args.verbose,
            probe_versions=args.verbose,
        )
        color = _should_colorize(
            args.color,
            plain=args.plain,
            stream=sys.stdout,
        )
        if args.json_output:
            print(render_env_json(env_snapshot, verbose=args.verbose))
        else:
            print(
                render_env_human(
                    env_snapshot,
                    verbose=args.verbose,
                    color=color,
                    abs_paths=args.abs_paths,
                    compact=args.compact,
                    show_home=args.show_home or args.show_all,
                    show_tools=args.show_tools or args.show_all,
                    show_hints=args.show_hints or args.show_all,
                ),
            )
        return 0

    repo_compact = not args.non_compact
    if args.stash_limit < 0:
        parser.error("--stash-limit must be non-negative")
    if args.release and not args.github:
        parser.error("--release requires --github")
    if not args.github and args.max_age:
        parser.error("--max-age requires --github")
    _validate_remote_options(parser, max_age=args.max_age, timeout=args.timeout)

    from quick_status.git_snapshot import RepoSnapshotError, collect_repo_snapshot
    from quick_status.repo_render import (
        render_repo_github_lines,
        render_repo_human,
        render_repo_json,
        render_repo_local_lines,
        render_repo_verbose_lines,
    )

    try:
        repo_snapshot = collect_repo_snapshot(
            cwd,
            include_github=args.github,
            include_commands=args.verbose,
            include_stashes=args.stashes,
            stash_limit=args.stash_limit,
            include_details=args.json_output or args.verbose,
            include_worktrees=args.worktrees or args.json_output or args.verbose,
        )
    except RepoSnapshotError as exc:
        if args.json_output:
            print(
                json.dumps(
                    {"error": str(exc), "schema_version": "quick_status_error_v1"},
                    sort_keys=True,
                ),
            )
        else:
            print(f"quick-status: {exc}", file=sys.stderr)
        return 2

    color = _should_colorize(
        args.color,
        plain=args.plain,
        stream=sys.stdout,
    )
    if args.github and not args.json_output:
        _print_lines(
            render_repo_local_lines(
                repo_snapshot,
                color=color,
                compact=repo_compact,
                show_worktrees=args.worktrees,
                show_stashes=args.stashes,
            ),
            flush=True,
        )

    if args.github:
        from quick_status.github import collect_github_context, enrich_repo_snapshot

        github, github_commands = collect_github_context(
            repo=repo_snapshot.repo.github_repo,
            branch=repo_snapshot.branch,
            root=Path(repo_snapshot.repo.root),
            include_commands=args.verbose,
            include_release=args.release,
            max_age_s=args.max_age,
            timeout_s=args.timeout,
        )
        repo_snapshot = enrich_repo_snapshot(
            repo_snapshot,
            github,
            github_commands,
        )

    if args.json_output:
        print(render_repo_json(repo_snapshot, verbose=args.verbose))
    elif args.github:
        _print_lines(
            render_repo_github_lines(
                repo_snapshot,
                color=color,
                compact=repo_compact,
            ),
        )
        if args.verbose:
            _print_lines(
                render_repo_verbose_lines(
                    repo_snapshot,
                    color=color,
                    compact=repo_compact,
                ),
            )
    else:
        print(
            render_repo_human(
                repo_snapshot,
                verbose=args.verbose,
                color=color,
                compact=repo_compact,
                show_worktrees=args.worktrees,
                show_stashes=args.stashes,
            ),
        )
    return 0


def _print_lines(lines: list[str], *, flush: bool = False) -> None:
    """Print pre-rendered human lines, optionally flushing for progressive output."""
    if not lines:
        return
    print("\n".join(lines), flush=flush)


def _run_batch(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    workset: bool,
) -> int:
    """Collect and render an explicit repository batch."""
    from quick_status.batch import collect_repo_batch, discover_workset_repositories
    from quick_status.batch_render import render_batch_human, render_batch_json

    if args.workers <= 0:
        parser.error("--workers must be greater than zero")
    if args.release and not args.github:
        parser.error("--release requires --github")
    if not args.github and args.max_age:
        parser.error("--max-age requires --github")
    _validate_remote_options(parser, max_age=args.max_age, timeout=args.timeout)
    paths = args.paths
    if workset:
        try:
            paths = discover_workset_repositories(args.paths[0])
        except ValueError as exc:
            parser.error(str(exc))
        if not paths:
            parser.error(f"no immediate Git repositories in {args.paths[0]}")
    snapshot = collect_repo_batch(
        paths,
        workers=args.workers,
        include_github=args.github,
        include_release=args.release,
        include_commands=args.verbose,
        include_details=args.json_output or args.verbose,
        max_age_s=args.max_age,
        timeout_s=args.timeout,
    )
    color = _should_colorize(args.color, plain=args.plain, stream=sys.stdout)
    if args.json_output:
        print(render_batch_json(snapshot, verbose=args.verbose))
    else:
        print(render_batch_human(snapshot, color=color))
    return 2 if any(item.status == "error" for item in snapshot.items) else 0


def _validate_remote_options(
    parser: argparse.ArgumentParser,
    *,
    max_age: float,
    timeout: float,
) -> None:
    """Validate bounded remote collection and explicit cache options."""
    if max_age < 0:
        parser.error("--max-age must be non-negative")
    if timeout <= 0:
        parser.error("--timeout must be greater than zero")


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
