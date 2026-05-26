# API

`quick-status` exposes one package metadata value and three read-only CLI snapshots:

- `quick-status repo`: local Git facts, with optional GitHub enrichment
- `quick-status env`: Python/project environment facts
- `quick-status ci`: deeper GitHub CI facts for the current branch or PR

```python
import quick_status

print(quick_status.__version__)
```

## Commands

```bash
quick-status
quick-status repo
quick-status repo --json
quick-status repo --github
quick-status repo --non-compact
quick-status repo --worktrees
quick-status repo --stashes --stash-limit 5
quick-status env
quick-status env --json
quick-status env --compact
quick-status env --show-all
quick-status ci
quick-status ci --json
quick-status ci --log-tail 40
quick-status --version
```

`quick-status` is an alias for `quick-status repo`. The default repo command only reads
local Git state. It does not fetch, mutate refs, run workflows, or call GitHub.

`quick-status env` inspects the active shell, Python runtime, project markers,
optional `devpy` config, and common tools. It does not activate environments,
install packages, or modify the project.

`quick-status ci` composes local Git facts with read-only `gh` calls. It does not
fetch, push, rerun, cancel, watch, or open browser windows.

## Repo Snapshot

`quick-status repo --json` emits a stable object with:

```json
{
  "schema_version": "quick_status_repo_snapshot_v1",
  "repo": {},
  "branch": {},
  "changes": {},
  "worktree": {},
  "stashes": {},
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
- `worktree`: current worktree path and `git worktree list --porcelain` entries;
  entries include `is_current` so agents do not infer the current checkout from
  path strings
- `stashes`: repo-family stash count and optional bounded entries when
  `--stashes` is requested
- `submodules`: submodule presence and clean/changed/uninitialized/conflict
  counts
- `github`: optional `--github` PR, check, and release facts
- `summary`: neutral summary fields for sync, worktree, PR, and remote checks

Repo human output is compact by default. Use `--non-compact` for the sectioned
human summary.

`quick-status repo --worktrees` adds a human worktree section with path, branch,
commit, and factual flags such as `current`, `detached`, `bare`, and
`prunable`. It does not scan every worktree for dirt unless a future explicit
flag adds that behavior.

`quick-status repo --stashes` adds bounded stash detail rows. Use `--stash-limit N`
to choose the maximum number of entries. Stash detail collection uses read-only
stash-list/show commands and never applies, drops, pops, rewrites, or ranks
stashes.

## Environment Snapshot

`quick-status env --json` emits a stable object with:

```json
{
  "schema_version": "quick_status_env_snapshot_v1",
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
- `runtime`: the Python executable currently running `quick-status`
- `python_commands`: PATH facts for `python` and `python3`
- `project`: detected project root, pyproject metadata, lock/config markers, and
  `.venv` presence
- `devpy`: parsed `devpy.toml` facts when present
- `tools`: optional tool facts for `git`, `uv`, `conda`, `devpy`, `pip`, and
  `pip3`
- `hints`: command-shaped helper hints, such as `devpy python`

Env human output is sectioned by default. Use `--compact` for the dense
one-line-per-section summary. Optional sections are hidden by default; use
`--show-tools`, `--show-hints`, `--show-home`, or `--show-all` when needed.

Default env collection is path-based and avoids slow `--version` subprocesses.
Use `--verbose` for command evidence records and version probes.

## CI Snapshot

`quick-status ci --json` emits a stable object with:

```json
{
  "schema_version": "quick_status_ci_snapshot_v1",
  "repo": {},
  "branch": {},
  "changes": {},
  "github": {},
  "pull_request": {},
  "commits": {},
  "currentness": {},
  "checks": [],
  "runs": [],
  "jobs": [],
  "log_tails": [],
  "summary": {},
  "source_errors": []
}
```

Top-level sections:

- `repo`: root path, git dir, repo name, remotes, and detected GitHub repo
- `branch`: current branch, local HEAD, upstream, and sync facts
- `changes`: local worktree cleanliness so green CI is not confused with
  uncommitted local changes
- `github`: `gh` availability/auth status and selected GitHub repo
- `pull_request`: current branch PR facts when a PR exists
- `commits`: local, PR, upstream tracking, and expected SHA comparisons
- `currentness`: whether the CI evidence applies to the expected SHA
- `checks`: PR check rows from `gh pr checks`
- `runs`: GitHub Actions run rows from `gh run list`
- `jobs`: failed job rows for failed current runs
- `log_tails`: optional bounded failed-log tails when `--log-tail` is set
- `summary`: aggregate currentness and check/run buckets
- `source_errors`: bounded source-specific GitHub errors

Currentness values:

- `current`: local HEAD matches the PR head, or a no-PR run exists for local
  HEAD
- `stale`: local HEAD differs from the PR head, or the latest branch run is for
  a different SHA than expected
- `absent`: no run exists for the expected SHA
- `unknown`: GitHub data is unavailable or conflicting

`quick-status ci` exits `0` when it produces a snapshot, even if CI is failing,
stale, absent, cancelled, or unavailable. It exits `2` for local repo
inspection or CLI argument failures.

Human CI summaries include `applies_to_head=yes/no/unknown` so stale green or
red runs are not confused with CI evidence for the current expected commit.

## JSON And Verbose Evidence

JSON output is intended for tools and agents. Human formatting choices,
including color and compact/sectioned layout, do not affect JSON.

Verbose JSON includes a `commands` array with compact command evidence records.
Command evidence is omitted by default.

## Exit Codes

- `0`: the snapshot command succeeded, even if the repo is dirty, ahead, behind,
  missing optional env tools, or has failing, stale, absent, or unavailable
  remote checks.
- `2`: the requested repo command could not inspect the path as a Git worktree,
  could not run Git, or received invalid CLI arguments.

## GitHub Mode

`quick-status repo --github` uses read-only `gh` API calls. Missing `gh`, missing
auth, offline errors, or rate limits do not fail the local snapshot. They
produce `github.status = "unavailable"` with an error string.

For human output, GitHub mode prints and flushes local Git facts first, then
appends PR, CI, and release facts after the slower GitHub calls finish. JSON
output remains one complete object printed at the end.

`quick-status` reports facts only. It does not emit readiness labels or next-action
recommendations.

## Color And Paths

Human output uses ANSI color by default only when stdout is an interactive
terminal. `--json` is never colorized. `--plain` and `--color=never` force plain
human output, while `--color=always` forces ANSI color. Auto color honors
`NO_COLOR` and disables color when `TERM=dumb`.

Env human output compacts home-relative paths with `~` by default. Use
`quick-status env --abs-paths` when exact absolute paths are more useful.
