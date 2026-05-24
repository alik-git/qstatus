# API

`qstatus` exposes one package metadata value and two read-only CLI snapshots:

- `qstatus repo`: local Git facts, with optional GitHub enrichment
- `qstatus env`: Python/project environment facts

```python
import qstatus

print(qstatus.__version__)
```

## Commands

```bash
qstatus
qstatus repo
qstatus repo --json
qstatus repo --github
qstatus repo --non-compact
qstatus env
qstatus env --json
qstatus env --compact
qstatus env --show-all
qstatus --version
```

`qstatus` is an alias for `qstatus repo`. The default repo command only reads
local Git state. It does not fetch, mutate refs, run workflows, or call GitHub.

`qstatus env` inspects the active shell, Python runtime, project markers,
optional `devpy` config, and common tools. It does not activate environments,
install packages, or modify the project.

## Repo Snapshot

`qstatus repo --json` emits a stable object with:

```json
{
  "schema_version": "qstatus_repo_snapshot_v1",
  "repo": {},
  "branch": {},
  "changes": {},
  "worktree": {},
  "submodules": {},
  "github": {},
  "summary": {}
}
```

Top-level sections:

- `repo`: root path, git dir, repo name, remotes, and detected GitHub repo
- `branch`: current branch or detached HEAD, commit, upstream, ahead/behind, and
  neutral sync state
- `changes`: staged, unstaged, untracked, conflicted, stash, and shortstat
  counts
- `worktree`: current worktree path and `git worktree list --porcelain` entries
- `submodules`: submodule presence and clean/changed/uninitialized/conflict
  counts
- `github`: optional `--github` PR, check, and release facts
- `summary`: neutral summary fields for sync, worktree, PR, and remote checks

Repo human output is compact by default. Use `--non-compact` for the sectioned
human summary.

## Environment Snapshot

`qstatus env --json` emits a stable object with:

```json
{
  "schema_version": "qstatus_env_snapshot_v1",
  "shell": {},
  "runtime": {},
  "python_commands": {},
  "project": {},
  "devpy": {},
  "tools": {},
  "hints": {}
}
```

Top-level sections:

- `shell`: current cwd plus active conda/venv shell markers
- `runtime`: the Python executable currently running `qstatus`
- `python_commands`: PATH facts for `python` and `python3`
- `project`: detected project root, pyproject metadata, lock/config markers, and
  `.venv` presence
- `devpy`: parsed `devpy.toml` facts when present
- `tools`: optional tool facts for `git`, `uv`, `conda`, `devpy`, `pip`, `pip3`,
  and `py_runner`
- `hints`: command-shaped helper hints, such as `devpy python` and py_runner
  overlay commands

Env human output is sectioned by default. Use `--compact` for the dense
one-line-per-section summary. Optional sections are hidden by default; use
`--show-tools`, `--show-hints`, `--show-home`, or `--show-all` when needed.

Default env collection is path-based and avoids slow `--version` subprocesses.
Use `--verbose` for command evidence records and version probes.

## JSON And Verbose Evidence

JSON output is intended for tools and agents. Human formatting choices,
including color and compact/sectioned layout, do not affect JSON.

Verbose JSON includes a `commands` array with compact command evidence records.
Command evidence is omitted by default.

## Exit Codes

- `0`: the snapshot command succeeded, even if the repo is dirty, ahead, behind,
  missing optional env tools, or has failing remote checks.
- `2`: `qstatus repo` could not inspect the requested path as a Git worktree or
  could not run Git.

## GitHub Mode

`qstatus repo --github` uses read-only `gh` API calls. Missing `gh`, missing
auth, offline errors, or rate limits do not fail the local snapshot. They
produce `github.status = "unavailable"` with an error string.

For human output, GitHub mode prints and flushes local Git facts first, then
appends PR, CI, and release facts after the slower GitHub calls finish. JSON
output remains one complete object printed at the end.

`qstatus` reports facts only. It does not emit readiness labels or next-action
recommendations.

## Color And Paths

Human output uses ANSI color by default only when stdout is an interactive
terminal. `--json` is never colorized. `--plain` and `--color=never` force plain
human output, while `--color=always` forces ANSI color. Auto color honors
`NO_COLOR` and disables color when `TERM=dumb`.

Env human output compacts home-relative paths with `~` by default. Use
`qstatus env --abs-paths` when exact absolute paths are more useful.
