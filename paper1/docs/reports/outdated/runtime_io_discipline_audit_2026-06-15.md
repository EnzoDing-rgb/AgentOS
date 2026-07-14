# Runtime I/O Discipline Audit — June 15, 2026

## Filesystem Layout

| Path | Filesystem | Type |
|---|---|---|
| `/root/.dev/AgentOS` | overlayfs | Docker overlay on host NVMe |
| `/tmp` | overlayfs | Same layer (NOT tmpfs) |
| `/dev/shm` | tmpfs | Memory-backed, 528 GB free |
| `/Lishun` | nfs (vers=3) | Remote NFS — banned by runtime.py |

**Finding: no NFS bottleneck.** `/tmp` is local overlayfs, not NFS. The only NFS
mount (`/Lishun`) is explicitly banned by `runtime.py`'s preflight check.

## High-Frequency Write Points

1. git worktree add/reset/clean — thousands of small files per task
2. pip install -e . — editable install into worktree
3. pytest — `.pyc` files, cache dirs
4. trace steps.jsonl — one append per agent step
5. JSONL output — one append per completed task
6. checkpoint JSON — overwrite per task
7. heartbeat JSON — overwrite every 30s

## Bug: Stale pip Marker

`local_harness.py:_pip_marker_path()` stores markers in worktree **parent** dir.
When `_remove_worktree()` nukes the worktree, `.pip_ok` markers survive. If the
same `workspace_key` is reused, pip install is incorrectly skipped.

**Severity:** Low in practice (unique keys per run). Fix: store marker inside
worktree, or clean up in `_remove_worktree`.

## Recommended Layout

```
/tmp/budgetflow-runtime/          # overlayfs scratch (current default)
  worktrees/                      # git checkouts (high churn, safe to lose)
  repos/                          # bare/mirror clones (regenerable)
  traces/                         # per-step trace scratch
  locks/                          # fcntl flock files

paper1/data/runs/                 # evidence (keep permanently)
  *.jsonl, *.checkpoint.json, *.heartbeat.json
```

## tmpfs Option for Paid Runs

`/dev/shm` has 528 GB tmpfs. Using `--runtime-root /dev/shm/budgetflow-runtime`
makes git worktree ops and pip installs memory-backed. This is safe because:

- Worktrees and traces are treated as transient
- Final JSONL/checkpoint still land in `paper1/data/runs/` (persistent)
- Repos can be re-cloned after reboot

**Recommended for next paid run:**
```bash
--runtime-root /dev/shm/budgetflow-runtime
```

## Code Already Correct

- `--runtime-root` and `--worktree-root` CLI flags wired in `compare_cli.py`
- `runtime.py` has clean separation of worktrees/repos/traces/locks
- NFS preflight bans `/Lishun` prefix
- No general filesystem-type check (only `/Lishun` ban)
