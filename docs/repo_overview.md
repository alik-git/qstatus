# Repo Overview

`qstatus` is a small read-only status tool for humans and coding agents.

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

- `qstatus` / `qstatus repo`: local Git status snapshot
- `qstatus repo --github`: local Git facts plus read-only GitHub PR, CI, and
  release facts through `gh`
- `qstatus repo --json`: stable repo JSON
- `qstatus env`: Python/project environment snapshot
- `qstatus env --json`: stable environment JSON
- `qstatus ci`: detailed read-only GitHub CI snapshot
- `qstatus ci --json`: stable CI JSON

See [API](api.md) for the command and JSON contract.

## Module Ownership

- `cli.py`: argument parsing and command orchestration
- `git_snapshot.py`: local Git facts and parsing
- `github.py`: optional GitHub facts through `gh`
- `ci_snapshot.py`: detailed CI facts through `gh`
- `env_snapshot.py`: Python, shell, project, `devpy`, and tool facts
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
- Missing optional tools are facts, not crashes.
- JSON is the stable machine contract; human output can evolve for readability.
- Repo output is compact by default; env output is sectioned by default.
- `qstatus ci` can be slower than `repo --github`, but it should remain a
  factual read-only diagnostic rather than a GitHub Actions control plane.
- No readiness classifier belongs in qstatus. Callers can judge readiness from
  the facts.

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
