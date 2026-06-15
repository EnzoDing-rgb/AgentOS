"""Auto-increment run stems under data/runs/ with sibling detection.

Every stem allocation writes a PID-based lock file so concurrent processes
cannot accidentally share the same logical run identity.  Sibling stems
(multiple -N suffixes for the same series base) are detected and blocked
unless the run is explicitly marked as a repair or shard.
"""

from __future__ import annotations

import atexit
import json
import os
import re
from pathlib import Path
from collections.abc import Callable, Iterable

_SERIES_STEM_RE = re.compile(r"^(?P<base>.+)-(?P<idx>\d+)$")
_LOCK_EXT = ".lock"
ScoreableKey = tuple[str, str]


def default_series_base(*, tasks_n: int, strategies_n: int, task_set: str = "easy") -> str:
    """Default series prefix from experiment shape (no manual -N suffix)."""
    prefix = "policy" if task_set == "medium" else "compare"
    return f"{prefix}_{tasks_n}x{strategies_n}"


# ── PID-based lock file ──────────────────────────────────────────────────

def _lock_path(stem: str, runs_dir: Path) -> Path:
    return runs_dir / f"{stem}{_LOCK_EXT}"


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check: /proc/<pid> exists."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _acquire_stem_lock(stem: str, runs_dir: Path) -> None:
    """Write a PID lock file for *stem*.  Refuses if another live process holds it."""
    lock = _lock_path(stem, runs_dir)
    if lock.exists():
        try:
            owner_pid = int(lock.read_text().strip())
        except (ValueError, OSError):
            pass
        else:
            if _pid_alive(owner_pid) and owner_pid != os.getpid():
                raise SystemExit(
                    f"stem {stem!r} is locked by PID {owner_pid} (still alive). "
                    f"Another process is writing to this run. "
                    f"Wait for it to finish, or use a different --run-series / --out-stem."
                )
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))
    atexit.register(_release_stem_lock, stem, runs_dir)


def _release_stem_lock(stem: str, runs_dir: Path) -> None:
    lock = _lock_path(stem, runs_dir)
    try:
        owner_pid = int(lock.read_text().strip())
        if owner_pid != os.getpid():
            return
        lock.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def release_run_identity(stem: str, runs_dir: Path) -> None:
    """Release the PID lock for a resolved compare run stem."""
    _release_stem_lock(stem, runs_dir)


# ── Sibling detection ────────────────────────────────────────────────────

def detect_sibling_stems(runs_dir: Path, series: str) -> list[str]:
    """Return all stems for *series* if more than one exists (sibling fragmentation).

    A single logical experiment spread across multiple -N stems is a data
    integrity problem: results can be double-counted, costs can be inflated,
    and the run appears more complete than it actually is.
    """
    stems = list_series_stems(runs_dir, series)
    if len(stems) > 1:
        return stems
    return []


def sibling_stems_exist(runs_dir: Path, series: str) -> bool:
    return len(detect_sibling_stems(runs_dir, series)) > 0


# ── Stem allocation ──────────────────────────────────────────────────────

def allocate_series_stem(runs_dir: Path, series: str) -> str:
    """Return next unused stem for a series base and acquire its lock.

    Scans existing artifacts, picks max(idx)+1, then writes a PID lock so
    concurrent processes cannot claim the same stem.
    """
    best = -1
    if runs_dir.is_dir():
        for path in runs_dir.iterdir():
            stem = path.name.split(".", 1)[0]
            match = _SERIES_STEM_RE.match(stem)
            if match and match.group("base") == series:
                best = max(best, int(match.group("idx")))
    stem = f"{series}-{best + 1}"
    _acquire_stem_lock(stem, runs_dir)
    return stem


def list_series_stems(runs_dir: Path, series: str) -> list[str]:
    seen: set[str] = set()
    if not runs_dir.is_dir():
        return []
    for path in runs_dir.iterdir():
        stem = path.name.split(".", 1)[0]
        match = _SERIES_STEM_RE.match(stem)
        if match and match.group("base") == series:
            seen.add(stem)
    return sorted(seen, key=lambda s: int(_SERIES_STEM_RE.match(s).group("idx")))  # type: ignore[union-attr]


def latest_series_stem(runs_dir: Path, series: str) -> str | None:
    stems = list_series_stems(runs_dir, series)
    return stems[-1] if stems else None


def completed_scoreable_keys(
    jsonl_path: Path,
    *,
    normalize_strategy: Callable[[str], str] | None = None,
) -> set[ScoreableKey]:
    """Unique completed policy-task pairs from scoreable JSONL rows.

    Raw JSONL line count is not a run-completion contract: duplicate retries,
    abort rows, and partial writes are paid evidence but not completed
    scoreable pairs.  Resume idempotency is defined over pass/true_fail rows.
    """
    if not jsonl_path.is_file():
        return set()
    normalize = normalize_strategy or (lambda name: name)
    done: set[ScoreableKey] = set()
    for line in jsonl_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        score_status = str(record.get("score_status") or "")
        if score_status not in {"pass", "true_fail"}:
            continue
        strategy = normalize(str(record.get("strategy") or ""))
        instance_id = str(record.get("instance_id") or "")
        if strategy and instance_id:
            done.add((strategy, instance_id))
    return done


def series_run_complete(
    runs_dir: Path,
    stem: str,
    *,
    total_runs: int,
    expected_keys: Iterable[ScoreableKey] | None = None,
    normalize_strategy: Callable[[str], str] | None = None,
) -> bool:
    completed = completed_scoreable_keys(
        runs_dir / f"{stem}.jsonl",
        normalize_strategy=normalize_strategy,
    )
    if expected_keys is not None:
        expected = set(expected_keys)
        return bool(expected) and expected.issubset(completed)
    return len(completed) >= total_runs


def resolve_compare_stem(
    runs_dir: Path,
    *,
    series: str,
    resume: bool,
    total_runs: int,
    expected_keys: Iterable[ScoreableKey] | None = None,
    normalize_strategy: Callable[[str], str] | None = None,
    explicit_stem: str | None = None,
    repair: bool = False,
) -> tuple[str, str]:
    """Pick output stem. Returns (stem, mode) where mode is 'new' | 'resume' | 'repair'.

    *repair* allows working with a sibling-fragmented series that would
    otherwise be blocked.  Only the latest stem is targeted for repair.
    """
    if not repair:
        siblings = detect_sibling_stems(runs_dir, series)
        if siblings and not explicit_stem:
            raise SystemExit(
                f"sibling stems detected for series {series!r}: {', '.join(siblings)}. "
                f"This logical run is fragmented across {len(siblings)} output files. "
                f"Combine them manually with a repair script, or use --out-stem to "
                f"pin a specific stem for resume. "
                f"Re-run with --repair to acknowledge and target the latest stem."
            )

    if explicit_stem:
        if resume:
            jsonl = runs_dir / f"{explicit_stem}.jsonl"
            if not jsonl.is_file():
                raise SystemExit(
                    f"--resume --out-stem={explicit_stem}: {jsonl} does not exist. "
                    "Start without --resume to create a new run."
                )
            if series_run_complete(
                runs_dir,
                explicit_stem,
                total_runs=total_runs,
                expected_keys=expected_keys,
                normalize_strategy=normalize_strategy,
            ):
                raise SystemExit(
                    f"--resume --out-stem={explicit_stem}: run is already complete "
                    f"({total_runs}/{total_runs}). Use a new --out-stem for the next experiment."
                )
            _acquire_stem_lock(explicit_stem, runs_dir)
            return explicit_stem, "resume"
        jsonl = runs_dir / f"{explicit_stem}.jsonl"
        if jsonl.is_file() and not repair:
            raise SystemExit(
                f"refusing to overwrite {jsonl}; use --resume to continue it "
                f"or omit --out-stem to auto-allocate the next {series}-N"
            )
        _acquire_stem_lock(explicit_stem, runs_dir)
        return explicit_stem, "repair" if repair and jsonl.is_file() else "new"

    if resume:
        latest = latest_series_stem(runs_dir, series)
        if latest is None:
            raise SystemExit(
                f"--resume: no prior runs for series {series!r} under {runs_dir}. "
                "Start without --resume to create a new run."
            )
        if series_run_complete(
            runs_dir,
            latest,
            total_runs=total_runs,
            expected_keys=expected_keys,
            normalize_strategy=normalize_strategy,
        ):
            nxt = allocate_series_stem(runs_dir, series)
            raise SystemExit(
                f"--resume: latest {latest} is complete ({total_runs}/{total_runs}). "
                f"Drop --resume to start {nxt}"
            )
        _acquire_stem_lock(latest, runs_dir)
        return latest, "resume"

    stem = allocate_series_stem(runs_dir, series)
    return stem, "new"


def resolve_run_identity(
    runs_dir: Path,
    *,
    tasks_n: int,
    strategies_n: int,
    task_set: str,
    resume: bool,
    total_runs: int,
    expected_keys: Iterable[ScoreableKey] | None = None,
    normalize_strategy: Callable[[str], str] | None = None,
    explicit_stem: str | None = None,
    explicit_series: str | None = None,
    repair: bool = False,
) -> tuple[str, str, str, str]:
    """Resolve artifact identity.

    Returns (out_stem, stem_mode, series_base, run_series).  The series base is
    used only for auto-allocation/resume grouping.  The run_series written into
    JSONL/heartbeat must equal the concrete output stem so artifacts from
    repeated same-shape experiments cannot overwrite or cross-reference each
    other.
    """
    series_base = explicit_series or default_series_base(
        tasks_n=tasks_n,
        strategies_n=strategies_n,
        task_set=task_set,
    )
    out_stem, stem_mode = resolve_compare_stem(
        runs_dir,
        series=series_base,
        resume=resume,
        total_runs=total_runs,
        expected_keys=expected_keys,
        normalize_strategy=normalize_strategy,
        explicit_stem=explicit_stem,
        repair=repair,
    )
    return out_stem, stem_mode, series_base, out_stem
