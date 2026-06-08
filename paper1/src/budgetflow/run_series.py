"""Auto-increment run stems: policy_15x7-0, policy_15x7-1, ... under data/runs/."""

from __future__ import annotations

import json
import re
from pathlib import Path

_SERIES_STEM_RE = re.compile(r"^(?P<base>.+)-(?P<idx>\d+)$")


def default_series_base(*, tasks_n: int, strategies_n: int, task_set: str = "easy") -> str:
    """Default series prefix from experiment shape (no manual -N suffix)."""
    prefix = "policy" if task_set == "medium" else "compare"
    return f"{prefix}_{tasks_n}x{strategies_n}"


def allocate_series_stem(runs_dir: Path, series: str) -> str:
    """Return next unused stem for a series base (e.g. policy_15x7 → policy_15x7-9)."""
    best = -1
    if runs_dir.is_dir():
        for path in runs_dir.iterdir():
            stem = path.name.split(".", 1)[0]
            match = _SERIES_STEM_RE.match(stem)
            if match and match.group("base") == series:
                best = max(best, int(match.group("idx")))
    return f"{series}-{best + 1}"


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


def count_jsonl_records(jsonl_path: Path) -> int:
    if not jsonl_path.is_file():
        return 0
    count = 0
    for line in jsonl_path.read_text().splitlines():
        if line.strip():
            count += 1
    return count


def series_run_complete(runs_dir: Path, stem: str, *, total_runs: int) -> bool:
    return count_jsonl_records(runs_dir / f"{stem}.jsonl") >= total_runs


def resolve_compare_stem(
    runs_dir: Path,
    *,
    series: str,
    resume: bool,
    total_runs: int,
    explicit_stem: str | None = None,
) -> tuple[str, str]:
    """Pick output stem. Returns (stem, mode) where mode is 'new' | 'resume'."""
    if explicit_stem:
        if resume:
            jsonl = runs_dir / f"{explicit_stem}.jsonl"
            if not jsonl.is_file():
                raise SystemExit(
                    f"--resume --out-stem={explicit_stem}: {jsonl} does not exist. "
                    "Start without --resume to create a new run."
                )
            if series_run_complete(runs_dir, explicit_stem, total_runs=total_runs):
                raise SystemExit(
                    f"--resume --out-stem={explicit_stem}: run is already complete "
                    f"({total_runs}/{total_runs}). Use a new --out-stem for the next experiment."
                )
            return explicit_stem, "resume"
        jsonl = runs_dir / f"{explicit_stem}.jsonl"
        if jsonl.is_file():
            raise SystemExit(
                f"refusing to overwrite {jsonl}; use --resume to continue it "
                f"or omit --out-stem to auto-allocate the next {series}-N"
            )
        return explicit_stem, "new"

    if resume:
        latest = latest_series_stem(runs_dir, series)
        if latest is None:
            raise SystemExit(
                f"--resume: no prior runs for series {series!r} under {runs_dir}. "
                f"Start without --resume to create {allocate_series_stem(runs_dir, series)}"
            )
        if series_run_complete(runs_dir, latest, total_runs=total_runs):
            nxt = allocate_series_stem(runs_dir, series)
            raise SystemExit(
                f"--resume: latest {latest} is complete ({total_runs}/{total_runs}). "
                f"Drop --resume to start {nxt}"
            )
        return latest, "resume"

    return allocate_series_stem(runs_dir, series), "new"


def resolve_run_identity(
    runs_dir: Path,
    *,
    tasks_n: int,
    strategies_n: int,
    task_set: str,
    resume: bool,
    total_runs: int,
    explicit_stem: str | None = None,
    explicit_series: str | None = None,
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
        explicit_stem=explicit_stem,
    )
    return out_stem, stem_mode, series_base, out_stem
