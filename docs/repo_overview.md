# Repo Overview

`quick-status` is a small read-only status tool for humans and coding agents.

It answers two questions quickly:

- What is the current Git/repo state?
- What Python/project environment would this command run in?
- What GitHub CI evidence exists for the current branch or PR?

The tool reports facts. It does not decide whether a repo is ready to commit,
push, merge, or release.

## Mental Model

At a high level:

1. snapshot collectors read local facts without mutating anything;
2. optional enrichers add slower external facts only when requested;
3. renderers turn the same snapshot into human output or stable JSON;
4. the CLI chooses the command, flags, color mode, and output shape.

Local facts should be fast and reliable. Slow checks, version probes, and
GitHub calls must stay explicit.

## Public Surface

- `quick-status` / `quick-status repo`: local Git status snapshot
- `quick-status repo --github`: local Git facts plus read-only GitHub PR, CI, and
  release facts through `gh`
- `quick-status repo --worktrees`: local Git facts plus linked worktree inventory
- `quick-status repo --stashes`: local Git facts plus bounded stash inventory
- `quick-status repo --json`: stable repo JSON
- `quick-status env`: Python/project environment snapshot
- `quick-status env --json`: stable environment JSON
- `quick-status ci`: detailed read-only GitHub CI snapshot
- `quick-status ci --json`: stable CI JSON
- `quick-status reminders init bash`: opt-in Bash source for command reminders,
  with interactive and guarded Codex contexts

See [API](api.md) for the command and JSON contract.

## Module Ownership

- `cli.py`: argument parsing and command orchestration
- `git_snapshot.py`: local Git facts and parsing
- `github.py`: optional GitHub facts through `gh`
- `ci_snapshot.py`: detailed CI facts through `gh`
- `env_snapshot.py`: Python, shell, project, `devpy`, and tool facts
- `reminders.py`: resource loading and context selection for opt-in reminders
- `shell/reminders.bash`: generated Bash integration source for reminder wrappers
- `models.py`: dataclass snapshot schemas
- `ci_models.py`: detailed CI snapshot schemas
- `repo_render.py`: repo human/JSON rendering
- `ci_render.py`: CI human/JSON rendering
- `env_render.py`: environment human/JSON rendering
- `formatting.py`: shared terminal formatting primitives
- `commands.py`: safe subprocess wrapper and command evidence records

Collectors own meaning. Renderers own presentation. The CLI should stay thin.

## Design Rules

- Default commands must stay read-only and fast.
- GitHub, CI, and version probes are opt-in because they can be slow or
  unavailable.
- Expanded repo-family inventories, such as linked worktrees and stash details,
  are explicit flags. The default repo command stays compact.
- Missing optional tools are facts, not crashes.
- JSON is the stable machine contract; human output can evolve for readability.
- Repo output is compact by default; env output is sectioned by default.
- `quick-status ci` can be slower than `repo --github`, but it should remain a
  factual read-only diagnostic rather than a GitHub Actions control plane.
- Shell reminders must stay opt-in and non-mutating. The default interactive
  context must remain interactive-only and terminal-stderr-only; the Codex
  context must stay guarded by Codex env vars and `bash -c` execution. The
  integration may suggest `quick-status`, but must not invoke it automatically.
- No readiness classifier belongs in quick-status. Callers can judge readiness from
  the facts.
- Worktree and stash reporting must stay factual: no safe-to-delete labels, no
  repair advice, and no mutation.

## Development Checks

For Python or packaging changes:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

For docs-only changes, at minimum check the relevant command help and run a
lightweight diff hygiene check.
