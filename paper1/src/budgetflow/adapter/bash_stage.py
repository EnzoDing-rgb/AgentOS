from __future__ import annotations

import re

from ..types import Stage

_LOCALIZATION_PATTERNS = (
    r"\bls\b",
    r"\bcat\b",
    r"\bhead\b",
    r"\btail\b",
    r"\bfind\b",
    r"\bgrep\b",
    r"\brg\b",
    r"\bwc\b",
    r"\bnl\b",
    r"sed -n",
    r"git log",
    r"git show",
    r"git status",
    r"git diff --stat",
)
_REPAIR_PATTERNS = (
    r"sed -i",
    r"perl\s+-.*-i",
    r"perl\s+-i",
    r"apply_patch",
    r"\bpatch\b",
    r"git apply",
    r"git checkout --",
    r">\s*[^\s]+\.(py|java|js|ts|rs|go|c|cpp|h)",
    r"cat <<",
    r"tee ",
    r"echo .+ >>",
)
_VALIDATION_PATTERNS = (
    r"\bpytest\b",
    r"python -m pytest",
    r"python -c",
    r"\bpip test\b",
    r"COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
)


_REPAIR_AGENT_PHASES = frozenset({"edit_gold", "edit_target", "edit_related", "edit_other", "patch_prep"})
_VALIDATION_AGENT_PHASES = frozenset({"test", "submit"})


def classify_bash_stage(bash_command: str | None, observation: str | None = None) -> Stage:
    command = (bash_command or "").strip()
    obs = (observation or "").lower()
    haystack = f"{command}\n{obs}".lower()

    if any(re.search(pattern, haystack) for pattern in _VALIDATION_PATTERNS):
        return Stage.VALIDATION
    if any(re.search(pattern, haystack) for pattern in _REPAIR_PATTERNS):
        return Stage.REPAIR
    if command and any(re.search(pattern, command, flags=re.IGNORECASE) for pattern in _LOCALIZATION_PATTERNS):
        return Stage.LOCALIZATION
    if obs and any(token in obs for token in ("error", "failed", "traceback", "assert", "pytest")):
        return Stage.VALIDATION
    return Stage.LOCALIZATION


def classify_routing_stage(
    bash_command: str | None,
    observation: str | None = None,
    *,
    agent_phase: str | None = None,
) -> Stage:
    """Merge bash heuristics with agent trace phase (edit_gold → repair, test → validation)."""
    phase = (agent_phase or "").strip()
    if phase in _REPAIR_AGENT_PHASES:
        return Stage.REPAIR
    if phase in _VALIDATION_AGENT_PHASES:
        return Stage.VALIDATION
    return classify_bash_stage(bash_command, observation)
