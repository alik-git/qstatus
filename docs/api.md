# API

`quick-status` exposes one package metadata value, four read-only CLI snapshots,
and one opt-in shell integration source command:

- `quick-status repo`: local Git facts, with optional GitHub enrichment
- `quick-status repos` / `workset`: bounded multi-repository facts
- `quick-status env`: Python/project environment facts
- `quick-status ci`: deeper GitHub CI facts for the current branch or PR
- `quick-status reminders init bash`: Bash source for optional command reminders

```python
import quick_status

print(quick_status.__version__)
```

## Commands

```bash
quick-status
quick-status /path/to/repo
quick-status repo
quick-status repo --json
quick-status repo --github
quick-status repo --github --release
quick-status repo --github --max-age 5
quick-status repo --non-compact
quick-status repo --worktrees
quick-status repo --stashes --stash-limit 5
quick-status repos /path/to/repo-a /path/to/repo-b
quick-status workset /path/to/workset
quick-status env
quick-status env --json
quick-status env --compact
quick-status env --show-all
quick-status ci
quick-status ci --json
quick-status ci --log-tail 40
quick-status ci --max-age 5
quick-status reminders init bash
quick-status reminders init bash --context codex
quick-status --version
```

`quick-status` is an alias for `quick-status repo`; an optional positional path
selects the repository. The default repo command only reads local Git state. It
does not fetch, mutate refs, run workflows, or call GitHub. Ahead/behind and
sync values are explicitly sourced from local remote-tracking refs and do not
imply that a fetch occurred.

`quick-status repos` concurrently inspects explicit paths in one process.
`quick-status workset` inspects only immediate Git children of an explicit
workset directory. Neither command recursively discovers repositories.

`quick-status env` inspects the active shell, Python runtime, project markers,
optional `veneer` config, and common tools. It does not activate environments,
install packages, or modify the project.

`quick-status ci` composes local Git facts with read-only `gh` calls. It does not
fetch, push, rerun, cancel, watch, or open browser windows.

`quick-status reminders init bash` prints Bash source for an opt-in shell
integration. The default context is for interactive shells; the Codex context is
for guarded non-interactive Codex command shells. The command does not modify
shell config files, invoke `quick-status`, or write JSON.

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
- `github`: optional `--github` PR/check facts and remote evidence freshness;
  release facts appear only with `--release`
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

## Batch Snapshot

`quick-status repos ... --json` and `quick-status workset DIR --json` emit:

```json
{
  "schema_version": "quick_status_repo_batch_v1",
  "items": [
    {
      "path": "/path/to/repo",
      "status": "ok",
      "duration_ms": 84.2,
      "snapshot": {},
      "error": null
    }
  ]
}
```

Items preserve explicit input order; workset items use deterministic name
order. Invalid targets remain error items alongside successful snapshots.

## Environment Snapshot

`quick-status env --json` emits a stable object with:

```json
{
  "schema_version": "quick_status_env_snapshot_v1",
  "shell": {},
  "runtime": {},
  "python_commands": {},
  "project": {},
  "veneer": {},
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
- `veneer`: parsed `veneer.toml` (or `notuv.toml` / `devpy.toml`) facts when present
- `tools`: optional tool facts for `git`, `uv`, `conda`, `veneer`, `pip`, and
  `pip3`
- `hints`: command-shaped helper hints, such as `veneer python`

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
- `github`: `gh` availability, selected GitHub repo, and
  `source`/`collected_at`/`age_seconds` freshness
- `pull_request`: current branch PR facts when a PR exists
- `commits`: local, PR, upstream tracking, and expected SHA comparisons
- `currentness`: whether the CI evidence applies to the expected SHA
- `checks`: PR check rows from the PR query's `statusCheckRollup`
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

## Shell Reminders

`quick-status reminders init bash` emits source that can be loaded by Bash:

```bash
eval "$(quick-status reminders init bash)"
```

The generated source defines wrappers for a narrow set of status-oriented tools
and arguments. Matching successful commands keep their normal stdout/stderr
behavior, then print a reminder to stderr with the suggested `quick-status`
command.

The integration is intentionally opt-in and inert for non-interactive shells. It
prints reminders only when stderr is a terminal, preserves the wrapped command's
exit code, leaves existing shell functions and aliases untouched, and can be
disabled in a loaded shell with `QUICK_STATUS_REMINDERS=0`.

`quick-status reminders init bash --context codex` emits a separate guarded
context for Codex command tool shells. It can initialize in non-interactive
`bash -c` shells and may print reminders to captured stderr, but only when
`CODEX_THREAD_ID`, `CODEX_CI=1`, and `BASH_EXECUTION_STRING` are all present.
The default `interactive` context keeps the terminal-only behavior above.

## JSON And Verbose Evidence

JSON output is intended for tools and agents. Human formatting choices,
including color and compact/sectioned layout, do not affect JSON.

Verbose JSON includes a `commands` array with compact command evidence records,
including `duration_ms` and remote `source`/age fields. Command evidence is
omitted by default.

## Exit Codes

- `0`: the snapshot command succeeded, even if the repo is dirty, ahead, behind,
  missing optional env tools, or has failing, stale, absent, or unavailable
  remote checks.
- `2`: the requested repo command could not inspect the path as a Git worktree,
  could not run Git, or received invalid CLI arguments.

## GitHub Mode

`quick-status repo --github` uses read-only `gh` API calls. One branch-filtered
PR query also supplies the check rollup. With no PR, one exact-commit workflow
query supplies check state. Missing `gh` or auth produces `unavailable`;
timeouts, invalid JSON, offline failures, and rate limits remain explicit
errors instead of becoming absent PRs or runs.

For human output, GitHub mode prints and flushes local Git facts first, then
appends PR and CI facts after the slower GitHub calls finish. JSON
output remains one complete object printed at the end.

`--release` adds an explicit project-version release lookup. `--timeout`
provides one overall GitHub deadline. `--max-age` explicitly enables caching of
successful JSON responses; default remote collection is live. Cached output
includes collection time and age, transient errors are never cached, and
`QUICK_STATUS_CACHE_DIR` can override the cache directory.

`quick-status` reports facts only. It does not emit readiness labels or next-action
recommendations.

## Color And Paths

Human output uses ANSI color by default only when stdout is an interactive
terminal. `--json` is never colorized. `--plain` and `--color=never` force plain
human output, while `--color=always` forces ANSI color. Auto color honors
`NO_COLOR` and disables color when `TERM=dumb`.

Env human output compacts home-relative paths with `~` by default. Use
`quick-status env --abs-paths` when exact absolute paths are more useful.
