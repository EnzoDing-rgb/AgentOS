"""BudgetFlow runtime path configuration.

Three-layer directory strategy:
  /root/.dev/AgentOS               — source code, docs, persistent results
  /tmp/budgetflow-runtime          — high-churn scratch (worktrees, repos, locks, traces)
  paper1/data/runs                 — persistent evidence (JSONL, checkpoint, heartbeat)

Principle: /tmp holds everything that can be regenerated; data/runs holds the evidence.

Usage:
  # Priority: CLI > BUDGETFLOW_RUNTIME_ROOT env > default
  from budgetflow.runtime import set_runtime_root, get_runtime_root
  set_runtime_root("/custom/runtime/path")  # before first use
  root = get_runtime_root()  # -> Path("/tmp/budgetflow-runtime")
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Global state ────────────────────────────────────────────────────────────

_RUNTIME_ROOT: Path | None = None
_RUNTIME_ROOT_SOURCE = "default"

# Old NFS path that must never be used as runtime root.
_BANNED_PREFIX = "/Lishun"

# ── Validation ──────────────────────────────────────────────────────────────

def _check_not_banned(p: Path, label: str) -> None:
    resolved = str(p.resolve())
    if resolved.startswith(_BANNED_PREFIX):
        raise SystemExit(
            f"RUNTIME CONFIG ERROR: {label} points to old /Lishun path: {resolved}\n"
            f"  Use /tmp/budgetflow-runtime or another non-NFS location.\n"
            f"  Old /Lishun paths cause Git worktree deadlocks and NFS I/O stalls."
        )

# ── Resolution ──────────────────────────────────────────────────────────────

def resolve_runtime_root() -> tuple[Path, str]:
    """Return (root, source). Source: 'cli', 'env', 'default'."""
    global _RUNTIME_ROOT, _RUNTIME_ROOT_SOURCE
    if _RUNTIME_ROOT is not None:
        return _RUNTIME_ROOT, _RUNTIME_ROOT_SOURCE

    env_val = os.environ.get("BUDGETFLOW_RUNTIME_ROOT")
    if env_val:
        p = Path(env_val)
        _check_not_banned(p, "BUDGETFLOW_RUNTIME_ROOT env")
        p.mkdir(parents=True, exist_ok=True)
        _RUNTIME_ROOT = p
        _RUNTIME_ROOT_SOURCE = "env"
        return p, "env"

    default = Path("/tmp/budgetflow-runtime")
    _check_not_banned(default, "default runtime root")
    default.mkdir(parents=True, exist_ok=True)
    _RUNTIME_ROOT = default
    _RUNTIME_ROOT_SOURCE = "default"
    return default, "default"


def set_runtime_root(path: Path | str | None, *, allow_nfs: bool = False) -> None:
    """Override runtime root (call before any get_* function).

    Args:
        path: New runtime root path, or None to reset to default.
        allow_nfs: If True, skip the /Lishun NFS safety check.
    """
    global _RUNTIME_ROOT, _RUNTIME_ROOT_SOURCE
    if path is None:
        _RUNTIME_ROOT = None
        _RUNTIME_ROOT_SOURCE = "default"
        return
    p = Path(path)
    if not allow_nfs:
        _check_not_banned(p, "--runtime-root")
    p.mkdir(parents=True, exist_ok=True)
    _RUNTIME_ROOT = p
    _RUNTIME_ROOT_SOURCE = "cli"


def get_runtime_root() -> Path:
    root, _ = resolve_runtime_root()
    return root


def get_runtime_root_source() -> str:
    _, source = resolve_runtime_root()
    return source


# ── Subdirectory getters ────────────────────────────────────────────────────

def get_worktree_root() -> Path:
    """Runtime worktree checkouts: {runtime_root}/worktrees/"""
    p = get_runtime_root() / "worktrees"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_repo_cache_dir() -> Path:
    """Bare mirror clones for git worktree operations: {runtime_root}/repos/"""
    p = get_runtime_root() / "repos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_locks_dir() -> Path:
    """Cross-process fcntl.flock files: {runtime_root}/locks/"""
    p = get_runtime_root() / "locks"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_path_component(raw: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._=-" else "_" for ch in raw)


def get_trace_dir(instance_id: str, label: str, *, run_series: str = "") -> Path:
    """Per-task turn trace scratch.

    Current paid runs pass ``run_series`` so repeated task+strategy attempts do
    not overwrite submitted.patch evidence from earlier runs.
    """
    root = get_runtime_root() / "traces"
    if run_series:
        root = root / _safe_path_component(run_series)
    p = root / f"trace_{_safe_path_component(instance_id)}_{_safe_path_component(label)}"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Project root helpers ────────────────────────────────────────────────────

# runtime.py lives at <project_root>/paper1/src/budgetflow/runtime.py
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]   # /root/.dev/AgentOS
_PAPER1_ROOT = _THIS_FILE.parents[2]    # /root/.dev/AgentOS/paper1


def get_project_root() -> Path:
    """Repository root: /root/.dev/AgentOS."""
    return _PROJECT_ROOT


def get_paper1_root() -> Path:
    """Paper1 directory: /root/.dev/AgentOS/paper1."""
    return _PAPER1_ROOT


# ── External dependency resolution ──────────────────────────────────────────

def resolve_mini_swe_src() -> Path:
    """Find mini-swe-agent source dir.

    Priority: MINI_SWE_SRC env > repo external/.
    """
    env_val = os.environ.get("MINI_SWE_SRC")
    if env_val:
        p = Path(env_val)
        _check_not_banned(p, "MINI_SWE_SRC env")
        if (p / "src" / "minisweagent").is_dir():
            return p / "src"
        if (p / "minisweagent").is_dir():
            return p
        raise SystemExit(
            f"MINI_SWE_SRC={env_val} but minisweagent package not found under it."
        )

    # Repo-relative: <project_root>/external/mini-swe-agent/src
    repo_candidate = get_project_root() / "external" / "mini-swe-agent" / "src"
    if (repo_candidate / "minisweagent").is_dir():
        return repo_candidate

    raise SystemExit(
        "Cannot find mini-swe-agent. Set MINI_SWE_SRC env var to its src/ directory,\n"
        "  or ensure external/mini-swe-agent/src/minisweagent/ exists."
    )


def resolve_swebench_export_dir() -> Path | None:
    """Find SWE-bench lite export (test.jsonl, test.parquet).

    Priority: SWEBENCH_EXPORT_DIR env > paper1/data/swebench_lite_export/.
    Returns None if not found (caller falls back to HF download).
    """
    env_val = os.environ.get("SWEBENCH_EXPORT_DIR")
    if env_val:
        p = Path(env_val)
        _check_not_banned(p, "SWEBENCH_EXPORT_DIR env")
        if p.is_dir():
            return p

    local = get_paper1_root() / "data" / "swebench_lite_export"
    if local.is_dir():
        return local

    return None


# ── Startup diagnostics ─────────────────────────────────────────────────────

def print_runtime_info(runtime_root: Path, output_dir: Path, run_id: str, jobs: int) -> None:
    """Print startup path summary for audit trail."""
    print(f"[runtime] root={runtime_root}  source={get_runtime_root_source()}")
    print(f"[runtime] output_dir={output_dir}")
    print(f"[runtime] run_id={run_id}  jobs={jobs}")
    for name in ("worktrees", "repos", "locks", "traces"):
        print(f"[runtime]   {name} -> {runtime_root / name}")


def check_cwd() -> None:
    """Warn if running from old /Lishun path."""
    cwd = os.getcwd()
    if cwd.startswith(_BANNED_PREFIX):
        print(
            f"[runtime] WARNING: cwd is under old /Lishun path: {cwd}\n"
            f"  Development should be in /root/.dev/AgentOS.\n"
            f"  NFS paths may cause git slowness and worktree corruption.",
            flush=True,
        )


def is_nfs_or_banned(path: Path | str) -> bool:
    """Return True if path resolves to a banned /Lishun NFS prefix."""
    return str(Path(path).resolve()).startswith(_BANNED_PREFIX)
