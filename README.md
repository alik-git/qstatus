# qstatus

Quick local status snapshots for developer workspaces.

https://github.com/user-attachments/assets/a8baa40f-912b-4086-a6bc-755f8dbd501a

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
qstatus repo --non-compact
qstatus repo --color=always
qstatus env
qstatus env --cwd /path/to/project
qstatus env --json
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

Repo output is compact by default. Use `--non-compact` when you want the
sectioned human summary.

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

For human output, `--github` prints and flushes the local Git facts before
running GitHub checks, then appends PR, CI, and release facts when they are
ready. JSON output remains a single complete object printed at the end.

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

## Environment Snapshots

Use `qstatus env` to inspect Python, conda, venv, devpy, uv, and py_runner facts
without activating or modifying anything:

```bash
qstatus env
qstatus env --cwd ~/Projects/motion_data_processing_worktree1
qstatus env --show-all
qstatus env --show-tools --show-hints
qstatus env --abs-paths
qstatus env --compact
qstatus env --json
qstatus env --verbose
```

Example for a normal Python project:

```text
SHELL
  cwd  ~/Projects/qstatus
  kind=neutral  conda=none  venv=none
PYTHON
  runtime  ~/.local/share/uv/tools/qstatus/bin/python3
  python   missing
  python3  /usr/bin/python3
  version=3.14.4  venv_like=yes
PROJECT
  root  ~/Projects/qstatus
  pyproject=ok  uv.lock=yes  devpy=no  .venv=yes
```

Example for a `devpy`-backed worktree:

```text
PROJECT
  root  ~/Projects/motion_data_processing_worktree1
  name=motion-data-processing  pyproject=ok  uv.lock=yes  devpy=yes  .venv=yes
DEVPY
  venv  ~/Projects/motion_data_processing_worktree1/.venv
  base=mdp_shared  status=ok  venv_python=yes  editables=3
```

Use `--show-all`, `--show-tools`, `--show-hints`, or `--show-home` when you need
those extra sections:

```text
TOOLS
  uv  ~/.local/bin/uv
  conda  ~/miniconda3/condabin/conda
  devpy  ~/.local/bin/devpy
  py_runner  ~/.agent_files/py_runner/run
HINTS devpy_python=devpy python
      py_runner_overlay:
        ~/.agent_files/py_runner/run \
          --env mdp_shared \
          --python .venv/bin/python
```

`qstatus env` treats tools like `python`, `python3`, `pip`, `conda`, `devpy`,
`uv`, and `py_runner` as optional facts. Missing tools are reported as missing
instead of crashing the command. Human output compacts home-relative paths with
`~`; pass `--abs-paths` when exact absolute paths are more useful. Default env
collection is path-based and avoids slow `--version` subprocesses; use
`--verbose` when you want those command records and version probes. `qstatus
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
