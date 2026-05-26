# AGENTS.md

Repo-specific instructions for agents working with the `quick-status` package.

## Package Conventions

- Keep importable package code under `src/quick_status/`.
- Put CLI entrypoint behavior in `src/quick_status/cli.py`.

## Validation

- Run checks relevant to the files changed.
- For README/docs-only changes, run formatting and pre-commit hygiene.
- For Python or packaging changes, also run Ruff, mypy, pytest, and build
  checks.

## Pull Requests

- Use `.github/PULL_REQUEST_TEMPLATE.md` for PR descriptions.
- Do not commit secrets, credentials, local runtime config, or scratch notes.
- Keep `AGENTS.md` updated when recurring agent instructions become
  repo-specific.
