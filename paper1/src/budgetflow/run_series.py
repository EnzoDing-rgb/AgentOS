"""Auto-increment run stems: policy_5x7-0, policy_5x7-1, ... under data/runs/."""

from __future__ import annotations

import re
from pathlib import Path

_SERIES_STEM_RE = re.compile(r"^(?P<base>.+)-(?P<idx>\d+)$")


def allocate_series_stem(runs_dir: Path, series: str) -> str:
    """Return next unused stem for a series base (e.g. policy_5x7 → policy_5x7-1)."""
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
