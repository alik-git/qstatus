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
qstatus --version
```

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
