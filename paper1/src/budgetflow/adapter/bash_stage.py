from __future__ import annotations

import re
from pathlib import Path

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
    r"\bcp\s+",
    r"\bmv\s+",
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


_FILE_EXT = (
    r"py|pyx|pxd|pxi|md|rst|txt|cfg|ini|yml|yaml|json|toml|sh|bash|"
    r"js|ts|tsx|jsx|java|rs|go|c|cpp|h|hpp|css|scss|html|xml|sql|rb"
)

# Quoted paths: allow spaces between quotes
_QUOTED_PATH_RE = re.compile(r"""['"]([^'"]+\.(?:""" + _FILE_EXT + r"""))['"]""")

# Unquoted paths: conservative, no spaces, lookahead trailing boundary
_UNQUOTED_PATH_RE = re.compile(
    r"(?:^|\s)([a-zA-Z0-9_\-./]+\.(?:" + _FILE_EXT + r"))(?=[\s\"'`]|\Z)",
)


def extract_text_file_paths(text: str | None) -> list[str]:
    """Extract file paths from arbitrary text (not just bash commands).

    Conservative, sorted, deduped. Handles quoted and unquoted paths.
    Filters out URLs, globs, and key-like strings.
    """
    text = (text or "").strip()
    if not text:
        return []
    paths: set[str] = set()
    stripped = text
    for m in _QUOTED_PATH_RE.finditer(text):
        raw = m.group(1).strip()
        if raw and "*" not in raw and "?" not in raw:
            paths.add(_normalize_path(raw))
            stripped = stripped.replace(m.group(0), " ", 1)
    for m in _UNQUOTED_PATH_RE.finditer(stripped):
        raw = m.group(1).strip()
        if raw and "*" not in raw and "?" not in raw:
            paths.add(_normalize_path(raw))
    return sorted(p for p in paths if not p.startswith(("http://", "https://", "git@")))


def extract_trace_file_paths(
    bash_command: str | None = None,
    assistant_content_head: str | None = None,
    parser_input_snippet: str | None = None,
) -> list[str]:
    """Extract touched file paths from all available text sources in a turn.

    Merges paths from bash command, assistant content, and parser input.
    Deduplicated and sorted.
    """
    all_paths: set[str] = set()
    for source in (bash_command, assistant_content_head, parser_input_snippet):
        all_paths.update(extract_text_file_paths(source))
    return sorted(all_paths)


def _normalize_path(raw: str) -> str:
    """Normalize a file path: strip leading ./ and collapse //."""
    clean = raw
    while clean.startswith("./"):
        clean = clean[2:]
    while "//" in clean:
        clean = clean.replace("//", "/")
    return clean


def extract_touched_file_paths(bash_command: str | None) -> list[str]:
    """Extract file paths touched by a bash command (conservative, sorted, deduped).

    Supports paths from: sed, cat, grep, rg, find, ls, python, pytest, etc.
    Handles quoted paths (with spaces) and unquoted paths. Returns stable-sorted,
    deduplicated list. Empty list if no recognizable paths or command is None.
    """
    command = (bash_command or "").strip()
    if not command:
        return []
    paths: set[str] = set()

    # Quoted paths first (may contain spaces); remove matched substrings
    # to prevent the unquoted regex from matching fragments of quoted paths.
    stripped = command
    for m in _QUOTED_PATH_RE.finditer(command):
        raw = m.group(1).strip()
        if raw and "*" not in raw and "?" not in raw:
            paths.add(_normalize_path(raw))
            stripped = stripped.replace(m.group(0), " ", 1)

    # Unquoted paths
    for m in _UNQUOTED_PATH_RE.finditer(stripped):
        raw = m.group(1).strip()
        if raw and "*" not in raw and "?" not in raw:
            paths.add(_normalize_path(raw))

    return sorted(p for p in paths if not p.startswith(("http://", "https://", "git@")))


def bash_has_progress(bash_command: str | None) -> tuple[bool, str]:
    """Return (has_progress, reason).

    reason is one of: ``"repair_pattern"``, ``"validation_pattern"``, ``"none"``.
    """
    command = (bash_command or "").strip()
    if not command:
        return False, "none"
    haystack = command.lower()
    if any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in _REPAIR_PATTERNS):
        return True, "repair_pattern"
    if any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in _VALIDATION_PATTERNS):
        return True, "validation_pattern"
    return False, "none"


def command_counts_as_progress(
    bash_command: str | None,
    *,
    agent_phase: str | None = None,
) -> tuple[bool, str]:
    """Return whether a turn should reset anti-stagnation counters.

    Agent phase is useful for routing stage, but it is too coarse for
    anti-spin. A read-only grep/sed inside an edit/repair phase should not
    reset no-progress counters; otherwise the agent can spend many turns
    inspecting or rewriting temp files while the runtime believes repair is
    advancing.
    """
    has_progress, reason = bash_has_progress(bash_command)
    if has_progress:
        return True, reason
    phase = (agent_phase or "").strip()
    if phase in _VALIDATION_AGENT_PHASES:
        return True, "validation_phase"
    return False, "none"


def actions_count_as_progress(actions: list[dict] | tuple[dict, ...] | None) -> tuple[bool, str]:
    """Return whether the model's current action should count as productive.

    ``command_counts_as_progress`` reads the previous observation context and
    drives runtime stagnation. This helper reads the action just emitted by the
    selected backend, so audit and learning can attribute productive T3 turns to
    the model that produced the edit/test command.
    """
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        has_progress, reason = bash_has_progress(action.get("command"))
        if has_progress:
            return True, f"action_{reason}"
    return False, "none"


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
