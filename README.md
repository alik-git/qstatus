# qstatus

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
qstatus
qstatus repo
qstatus repo --json
qstatus repo --github
qstatus repo --cwd /path/to/repo
qstatus repo --verbose
qstatus repo --plain
qstatus repo --color=always
qstatus --version
```

`qstatus` is an alias for `qstatus repo`. By default it performs a fast local
Git snapshot only. It does not fetch, push, pull, run tests, run builds, or call
network services.

Example human output:

```text
REPO qstatus /home/ali/Projects/qstatus
BRANCH main 6acc81f origin/main synced ahead=0 behind=0
STATE clean staged=0 unstaged=0 untracked=0 conflicts=0 stash=0
REMOTE origin git@github.com:alik-git/qstatus.git
SUBMODULES none
PR not-requested
CI not-requested
```

Use `--json` when another tool or agent should consume the snapshot:

```bash
qstatus repo --json
```

Use `--github` only when you want read-only GitHub context through the `gh` CLI:

```bash
qstatus repo --github
qstatus repo --json --github
```

GitHub mode reports PR, CI/check, and package-release facts when available. If
`gh` is missing, unauthenticated, offline, or rate-limited, the local snapshot
still succeeds and the GitHub section is marked unavailable.

`qstatus` reports facts and neutral summaries only. It intentionally does not
decide whether a repo is ready to commit, push, merge, or release.

Human output uses color automatically when stdout is an interactive terminal.
Machine-readable JSON is never colorized. To control ANSI color explicitly:

```bash
qstatus repo --plain        # no ANSI color
qstatus repo --color=never  # no ANSI color
qstatus repo --color=always # force ANSI color
```

`--plain` overrides `--color`. Automatic color also honors the standard
`NO_COLOR` environment variable and disables color when `TERM=dumb`.

## Development

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
PyPI project name: qstatus
Owner: alik-git
Repository name: qstatus
Workflow name: release.yml
Environment name: pypi
```

The workflow filename is `release.yml`; the display name inside that file is
`Release`, but PyPI wants the filename. The `pypi` environment should also exist
under the GitHub repository's environment settings.

Publishing is release-driven: normal pushes and pull requests build and test the
package, but publishing happens when a GitHub Release is published or the release
workflow is manually dispatched.
