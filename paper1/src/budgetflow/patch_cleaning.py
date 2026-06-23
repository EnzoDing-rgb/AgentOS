"""Patch cleaning helpers for scoreable SWE-style workspace diffs."""

from __future__ import annotations

from pathlib import PurePosixPath

SETUP_AND_LOCKFILE_NAMES = frozenset(
    {
        "Cargo.lock",
        "Pipfile.lock",
        "package-lock.json",
        "poetry.lock",
        "pnpm-lock.yaml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "yarn.lock",
    }
)

SETUP_AND_LOCKFILE_SUFFIXES = (
    ".egg-info/",
    ".lock",
)


def clean_scoreable_patch(patch: str | None) -> str:
    """Strip harness-noise hunks from a workspace diff.

    The runner still scores repository workspace edits only. This cleaner keeps
    that source of truth while removing files that commonly make SWE-bench
    patch application/evaluation fail for reasons unrelated to the code fix:
    setup/dependency files, binary patches, and non-ASCII paths.
    """
    if not patch or not patch.strip():
        return ""

    kept: list[str] = []
    current: list[str] = []
    skip_current = False

    def flush() -> None:
        nonlocal current, skip_current
        if current and not skip_current:
            kept.extend(current)
        current = []
        skip_current = False

    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            flush()
            current = [line]
            paths = _paths_from_diff_header(line)
            skip_current = any(_drop_patch_path(path) for path in paths)
            continue
        current.append(line)
        if line.startswith("Binary files") or line.startswith("GIT binary patch"):
            skip_current = True

    flush()
    cleaned = "".join(kept)
    if not cleaned.strip():
        return ""
    return cleaned if cleaned.endswith("\n") else f"{cleaned}\n"


def _paths_from_diff_header(line: str) -> tuple[str, ...]:
    parts = line.strip().split()
    paths: list[str] = []
    for raw in parts[2:4]:
        if raw.startswith(("a/", "b/")):
            paths.append(raw[2:])
    return tuple(paths)


def _drop_patch_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if _has_non_ascii(normalized):
        return True
    pure = PurePosixPath(normalized)
    if pure.name in SETUP_AND_LOCKFILE_NAMES:
        return True
    return any(suffix in normalized for suffix in SETUP_AND_LOCKFILE_SUFFIXES)


def _has_non_ascii(text: str) -> bool:
    return any(ord(ch) > 127 for ch in text)
