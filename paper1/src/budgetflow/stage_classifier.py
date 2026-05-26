from __future__ import annotations

from .types import Stage


def classify_stage(tool_name: str | None, observation: str | None = None) -> Stage:
    if tool_name in {"apply_edits", "submit_patch"}:
        return Stage.REPAIR
    if tool_name in {"read_file", "grep", "glob", "search_defs"}:
        return Stage.LOCALIZATION
    if observation:
        lower = observation.lower()
        if "harness_fail" in lower or "pytest" in lower or "fail_after=fail" in lower:
            return Stage.VALIDATION
        if "edits applied" in lower or "diff --git" in lower:
            return Stage.REPAIR
    return Stage.LOCALIZATION
