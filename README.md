# quick-status

Quick local status snapshots for developer workspaces.

## Installation

Recommended with `uv`:

```bash
uv sync --extra dev
```

Standard Python fallback:

```bash
python -m pip install -e ".[dev]"
```

## Usage

```bash
quick-status
quick-status repo
quick-status repo --json
quick-status repo --github
quick-status repo --cwd /path/to/repo
quick-status repo --verbose
quick-status repo --plain
quick-status repo --non-compact
quick-status repo --worktrees
quick-status repo --stashes --stash-limit 5
quick-status repo --color=always
quick-status env
quick-status env --cwd /path/to/project
quick-status env --json
quick-status ci
quick-status ci --json
quick-status ci --cwd /path/to/repo
quick-status ci --log-tail 40
quick-status reminders init bash
quick-status reminders init bash --context codex
quick-status --version
```

`quick-status` is an alias for `quick-status repo`. By default it performs a fast local
Git snapshot only. It does not fetch, push, pull, run tests, run builds, or call
network services.

For even quicker personal shell usage, add a local alias:

```bash
alias qs='quick-status'
```

The package installs the explicit `quick-status` command; `qs` is intentionally
left as a shell-level shortcut so it cannot silently shadow another global
command on machines where that name is already used.

## Shell Reminders

Use the optional reminders integration when you want interactive Bash sessions
to nudge habitual status commands toward the matching `quick-status` snapshot:

```bash
eval "$(quick-status reminders init bash)"
```

The command prints shell source only. It does not edit shell config files,
invoke `quick-status`, or enable itself automatically. The generated integration
wraps a small set of exact, status-like commands such as `git status`, selected
`gh pr` or `gh run` checks, and environment probes such as `python3 --version`
or `which python3`.

Reminders print only after a matching command succeeds, preserve the original
exit code, and write to stderr only when stderr is an interactive terminal. They
skip non-interactive shells, captured stderr, failed commands, and commands
already implemented as shell functions or aliases, so scripts and existing
shell behavior should stay quiet. Set `QUICK_STATUS_REMINDERS=0` to disable
reminders in a shell where the integration has already been loaded.

A separate `--context codex` mode exists for tightly guarded Codex command
tool shells. It is meant to be loaded by a small `BASH_ENV` dispatcher, not by
normal shell startup. The generated source stays inert unless `CODEX_THREAD_ID`,
`CODEX_CI=1`, and `BASH_EXECUTION_STRING` are all present.

Example human output:

```text
REPO quick-status /home/ali/Projects/quick-status
BRANCH main 6acc81f origin/main synced ahead=0 behind=0
STATE clean staged=0 unstaged=0 untracked=0 conflicts=0 stash=0
REMOTE origin git@github.com:alik-git/quick-status.git
SUBMODULES none
PR not-requested
CI not-requested
```

Repo output is compact by default. Use `--non-compact` when you want the
sectioned human summary.

Use `--worktrees` when you want the linked worktree map for the current repo
family:

```bash
quick-status repo --worktrees
```

Use `--stashes` when you need bounded stash details in addition to the normal
stash count:

```bash
quick-status repo --stashes
quick-status repo --stashes --stash-limit 10
```

These are read-only inventory flags. They do not create, prune, apply, drop, or
repair anything.

Use `--json` when another tool or agent should consume the snapshot:

```bash
quick-status repo --json
```

Use `--github` only when you want read-only GitHub context through the `gh` CLI:

```bash
quick-status repo --github
quick-status repo --json --github
```

GitHub mode reports PR, CI/check, and package-release facts when available. If
`gh` is missing, unauthenticated, offline, or rate-limited, the local snapshot
still succeeds and the GitHub section is marked unavailable.

For human output, `--github` prints and flushes the local Git facts before
running GitHub checks, then appends PR, CI, and release facts when they are
ready. JSON output remains a single complete object printed at the end.

`quick-status` reports facts and neutral summaries only. It intentionally does not
decide whether a repo is ready to commit, push, merge, or release.

## CI Snapshots

Use `quick-status ci` when you need the deeper GitHub CI facts behind a branch or
PR:

```bash
quick-status ci
quick-status ci --cwd ~/Projects/myproject
quick-status ci --json
quick-status ci --verbose
quick-status ci --log-tail 40
```

`quick-status ci` is read-only. It does not fetch, push, rerun workflows, cancel
runs, or open a browser. It reports local `HEAD`, worktree cleanliness, the
current PR when one exists, expected SHA, current/stale/absent CI evidence,
check buckets, workflow run URLs, and failed job URLs.

Example no-PR output:

```text
CI quick-status alik-git/quick-status
BRANCH main local=4955870 upstream=origin/main synced
STATE clean staged=0 unstaged=0 untracked=0 conflicts=0
PR none
CURRENT current expected=4955870 checked=4955870 source=run-list-commit reason=run-exists-for-expected-sha
RUNS success total=1 pass=1 fail=0 pending=0 running=0 skipped=0 cancel=0 unknown=0 applies_to_head=yes
RUN Checks success id=26352434014 sha=4955870 currentness=current url=https://github.com/alik-git/quick-status/actions/runs/26352434014
```

`--log-tail N` is intentionally simple and opt-in. For failed current GitHub
Actions runs, it prints the last `N` non-empty lines from `gh run view
--log-failed`. If log fetching is unavailable, the snapshot still succeeds and
prints `LOG unavailable`.

Human output uses color automatically when stdout is an interactive terminal.
Machine-readable JSON is never colorized. To control ANSI color explicitly:

```bash
quick-status repo --plain        # no ANSI color
quick-status repo --color=never  # no ANSI color
quick-status repo --color=always # force ANSI color
```

`--plain` overrides `--color`. Automatic color also honors the standard
`NO_COLOR` environment variable and disables color when `TERM=dumb`.

## Environment Snapshots

Use `quick-status env` to inspect Python, conda, venv, veneer, and uv facts
without activating or modifying anything:

```bash
quick-status env
quick-status env --cwd ~/Projects/motion_data_processing_worktree1
quick-status env --show-all
quick-status env --show-tools --show-hints
quick-status env --abs-paths
quick-status env --compact
quick-status env --json
quick-status env --verbose
```

Example for a normal Python project:

```text
SHELL
  cwd  ~/Projects/quick-status
  kind=neutral  conda=none  venv=none
PYTHON
  runtime  ~/.local/share/uv/tools/quick-status/bin/python3
  python   missing
  python3  /usr/bin/python3
  version=3.14.4  venv_like=yes
PROJECT
  root  ~/Projects/quick-status
  pyproject=ok  uv.lock=yes  veneer=no  .venv=yes
```

Example for a `veneer`-backed worktree:

```text
PROJECT
  root  ~/Projects/motion_data_processing_worktree1
  name=motion-data-processing  pyproject=ok  uv.lock=yes  veneer=yes  .venv=yes
VENEER
  venv  ~/Projects/motion_data_processing_worktree1/.venv
  base=mdp_shared  status=ok  venv_python=yes  editables=3
```

Use `--show-all`, `--show-tools`, `--show-hints`, or `--show-home` when you need
those extra sections:

```text
TOOLS
  uv  ~/.local/bin/uv
  conda  ~/miniconda3/condabin/conda
  veneer  ~/.local/bin/veneer
HINTS veneer_python=veneer python
```

`quick-status env` treats tools like `python`, `python3`, `pip`, `conda`, `veneer`,
and `uv` as optional facts. Missing tools are reported as missing
instead of crashing the command. Human output compacts home-relative paths with
`~`; pass `--abs-paths` when exact absolute paths are more useful. Default env
collection is path-based and avoids slow `--version` subprocesses; use
`--verbose` when you want those command records and version probes. `quick-status
repo` still requires `git`, but reports a missing Git executable directly
instead of confusing it with a non-repository path.

## Development

Read these docs first when changing the package:

- [Repo Overview](docs/repo_overview.md): mental model, public surface, module
  ownership, and design rules
- [API](docs/api.md): command surface, JSON schemas, exit codes, GitHub mode,
  and env snapshot behavior

Run the standard checks before opening a PR:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

If you are using standard Python tools instead of uv:

```bash
python -m ruff format --check .
python -m ruff check .
python -m mypy
python -m pytest
python -m build
```

## Publishing

This repo publishes to PyPI through GitHub Actions Trusted Publishing. The
release workflow is [`.github/workflows/release.yml`](.github/workflows/release.yml).

Use these values in PyPI's pending trusted publisher form:

```text
PyPI project name: quick-status
Owner: alik-git
Repository name: quick-status
Workflow name: release.yml
Environment name: pypi
```

The workflow filename is `release.yml`; the display name inside that file is
`Release`, but PyPI wants the filename. The `pypi` environment should also exist
under the GitHub repository's environment settings.

Publishing is release-driven: normal pushes and pull requests build and test the
package, but publishing happens when a GitHub Release is published or the release
workflow is manually dispatched.
