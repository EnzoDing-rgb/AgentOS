from __future__ import annotations

import os
import site
import sys
from pathlib import Path


HOST_DEPENDENCY_CONTAMINATION_MARKERS = (
    "host_dependency_contamination:",
    "numpy.dtype size changed",
    "_ARRAY_API not found",
    "ConftestImportFailure",
    "ImportError while loading conftest",
    "ModuleNotFoundError: No module named",
    "opik/evaluation/metrics",
    "site-packages/tensorflow",
    "site-packages/keras",
    "site-packages/pandas",
    "/tmp/budgetflow-task-scout/runtime/worktrees/",
    "runtime worktree paths",
)

GLOBAL_PYTHON_PATH_CONTAMINATION_MARKERS = (
    "/tmp/budgetflow-runtime/worktrees",
    "/tmp/budgetflow-task-scout/",
    "/Lishun/",
)


def has_host_dependency_contamination(detail: str) -> bool:
    return any(marker in detail for marker in HOST_DEPENDENCY_CONTAMINATION_MARKERS)


def _python_path_contamination_marker(text: str, runtime_root: Path) -> str:
    runtime_worktrees = str((runtime_root / "worktrees").resolve())
    if runtime_worktrees in text:
        return runtime_worktrees
    for marker in GLOBAL_PYTHON_PATH_CONTAMINATION_MARKERS:
        if marker in text:
            return marker
    return ""


def is_runtime_worktree_path(raw: str, runtime_root: Path) -> bool:
    if not raw.strip():
        return False
    worktrees_root = (runtime_root / "worktrees").resolve()
    try:
        path = Path(raw.strip()).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return path == worktrees_root or worktrees_root in path.parents


def find_runtime_worktree_python_contamination(runtime_root: Path) -> list[str]:
    """Find global Python path state that imports one task worktree into another.

    The local SWE harness runs inside this container rather than official
    per-task Docker images.  A stale editable install under site-packages can
    therefore inject an old worktree into unrelated repositories.  Paid runs
    must fail before provider calls when this happens.
    """
    contaminated: list[str] = []

    site_dirs: list[str] = []
    try:
        site_dirs.extend(site.getsitepackages())
    except AttributeError:
        pass
    try:
        site_dirs.append(site.getusersitepackages())
    except AttributeError:
        pass

    for site_dir in dict.fromkeys(site_dirs):
        root = Path(site_dir)
        if not root.is_dir():
            continue
        for marker in sorted(root.glob("__editable___*_finder.py")):
            try:
                text = marker.read_text(errors="ignore")
            except OSError:
                continue
            bad_marker = _python_path_contamination_marker(text, runtime_root)
            if bad_marker:
                contaminated.append(f"{marker}: editable finder maps into {bad_marker}")
        for direct_url in sorted(root.glob("*.dist-info/direct_url.json")):
            try:
                text = direct_url.read_text(errors="ignore")
            except OSError:
                continue
            bad_marker = _python_path_contamination_marker(text, runtime_root)
            if bad_marker:
                contaminated.append(f"{direct_url}: editable install from {bad_marker}")
        for pth in sorted(root.glob("*.pth")):
            try:
                lines = pth.read_text(errors="ignore").splitlines()
            except OSError:
                continue
            bad_lines: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                bad_marker = _python_path_contamination_marker(stripped, runtime_root)
                if bad_marker:
                    bad_lines.append(stripped)
                elif not stripped.startswith("import ") and is_runtime_worktree_path(stripped, runtime_root):
                    bad_lines.append(stripped)
            if bad_lines:
                contaminated.append(f"{pth}: {', '.join(bad_lines[:3])}")

    pythonpath = os.environ.get("PYTHONPATH", "")
    for entry in [part for part in pythonpath.split(os.pathsep) if part]:
        if is_runtime_worktree_path(entry, runtime_root):
            contaminated.append(f"PYTHONPATH: {entry}")

    for path_entry in sys.path:
        if is_runtime_worktree_path(path_entry, runtime_root):
            contaminated.append(f"sys.path: {path_entry}")

    return contaminated


def format_runtime_worktree_contamination(contamination: list[str], *, limit: int = 6) -> str:
    preview = "; ".join(contamination[:limit])
    suffix = "" if len(contamination) <= limit else f"; ... +{len(contamination) - limit} more"
    return preview + suffix


def isolated_repo_pythonpath(repo_dir: Path, runtime_root: Path, existing: str | None = None) -> str:
    """Build a PYTHONPATH where the active repo is first and old worktrees are absent."""
    entries = [str(repo_dir)]
    for entry in (existing or "").split(os.pathsep):
        if not entry or entry == str(repo_dir):
            continue
        if is_runtime_worktree_path(entry, runtime_root):
            continue
        entries.append(entry)
    return os.pathsep.join(dict.fromkeys(entries))
