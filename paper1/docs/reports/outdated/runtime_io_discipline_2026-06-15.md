# Runtime / I/O Discipline Audit — 2026-06-15

## Objective

Check whether slow execution is plausibly caused by NFS or high-churn small-file
I/O, remove remaining `/Lishun` fallback paths, and document the runtime path
contract for paid BudgetFlow runs.

## Findings

| Path | Filesystem | Judgment |
|---|---|---|
| `/root/.dev/AgentOS` | Docker `overlay` | Current source workspace; not direct `/Lishun` NFS |
| `paper1/data/runs` | Docker `overlay` | Persistent evidence location |
| `/tmp` | Docker `overlay` | Local scratch location in this container |
| `/root` | Docker `overlay` | Local container filesystem |
| `/tmp/budgetflow-runtime` | Docker `overlay` | Default runtime scratch root |

Default runtime layout is correct:

- worktrees: `/tmp/budgetflow-runtime/worktrees`
- repo mirrors: `/tmp/budgetflow-runtime/repos`
- locks: `/tmp/budgetflow-runtime/locks`
- trace scratch: `/tmp/budgetflow-runtime/traces`
- persistent JSONL/checkpoint/summary: `paper1/data/runs`

The remaining technical debt was two symlinks to `/Lishun`:

- `external/mini-swe-agent`
- `paper1/data/swebench_lite_export`

Both are now localized into the current workspace and ignored by Git. Resolver
fallbacks to `/Lishun/_archive` were removed. If either dependency is missing,
the runtime now fails fast instead of silently reading from NFS.

## Mental Model

NFS is usually not slow because every small file creates a new network
connection. It is slow because small-file workloads generate many metadata
operations: `stat`, `open`, `rename`, directory scans, lock checks, and cache
coherency checks. SWE-bench runs amplify this pattern through git worktrees,
pytest discovery/cache, editable installs, trace files, checkpoints, and
heartbeats. Each operation is small, but the network round trips and lock
semantics dominate wall time.

## Runtime Contract

Use the repo for durable evidence:

- source code
- docs/reports
- docs/config
- value matrices
- frozen router plans
- budget plans
- final JSONL/checkpoint/summary evidence

Use local scratch for regenerable high-churn data:

- git worktrees
- repo mirrors
- locks
- trace scratch
- pytest cache
- editable install targets
- temporary build trees
- agent temp files

`/tmp` is valid scratch, not an evidence store.

## Code Changes

- `runtime.resolve_mini_swe_src()` no longer falls back to `/Lishun`.
- `runtime.resolve_swebench_export_dir()` no longer falls back to `/Lishun`.
- `/Lishun` env overrides for `MINI_SWE_SRC` and `SWEBENCH_EXPORT_DIR` now fail fast.
- `.gitignore` documents localized external/runtime dependencies and ignores local PDFs.
- `AGENTS.md` now states the runtime/I/O discipline.

## Next Paid Run Parameters

No extra override is needed when running inside this container:

```bash
--runtime-root /tmp/budgetflow-runtime
```

`--worktree-root` should normally be omitted; it is a deprecated escape hatch.
If used, it must also point to local scratch, not `/Lishun`.

## Verification

- `findmnt` shows `/root/.dev/AgentOS`, `/tmp`, and `/root` on Docker `overlay`.
- `external/mini-swe-agent` and `paper1/data/swebench_lite_export` are local directories, not symlinks.
- Runtime defaults resolve to `/tmp/budgetflow-runtime`.
