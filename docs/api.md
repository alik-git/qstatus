# API

`qstatus` exposes package metadata and a small read-only repo snapshot CLI.

```python
import qstatus

print(qstatus.__version__)
```

The command-line entry points are:

```bash
qstatus
qstatus repo
qstatus repo --json
qstatus repo --github
```

`qstatus` is an alias for `qstatus repo`. The default command only reads local
Git state. It does not fetch, mutate refs, run workflows, or call GitHub.

## JSON Schema

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

The top-level sections are:

- `repo`: root path, git dir, repo name, remotes, and detected GitHub repo.
- `branch`: current branch or detached HEAD, commit, upstream, ahead/behind, and
  neutral sync state.
- `changes`: staged, unstaged, untracked, conflicted, stash, and shortstat
  counts.
- `worktree`: current worktree path and `git worktree list --porcelain` entries.
- `submodules`: submodule presence and clean/changed/uninitialized/conflict
  counts.
- `github`: optional `--github` PR, check, and release facts.
- `summary`: neutral summary fields for sync, worktree, PR, and remote checks.

Verbose JSON includes a `commands` array with compact command evidence records.
Command evidence is omitted by default.

## Exit Codes

- `0`: the snapshot command succeeded, even if the repo is dirty, ahead, behind,
  or has failing remote checks.
- `2`: qstatus could not inspect the requested path as a Git worktree.

## GitHub Mode

`qstatus repo --github` uses `gh` read-only API calls. Missing `gh`, missing auth,
offline errors, or rate limits do not fail the local snapshot. They produce
`github.status = "unavailable"` with an error string.

The tool reports facts only. It does not emit readiness labels or next-action
recommendations.
