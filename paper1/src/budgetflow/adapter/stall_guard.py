"""Detect agent command loops / read-only streaks (strategy-agnostic)."""

from __future__ import annotations

from collections import deque

from ..defaults import STAGNATION_NO_PROGRESS_STEPS, STAGNATION_REPEAT_CMD_LIMIT


def normalize_bash_command(command: str | None) -> str:
    return " ".join((command or "").split())


def repeat_command_streak(commands: deque[str], *, limit: int) -> tuple[bool, str | None]:
    if limit <= 0 or len(commands) < limit:
        return False, None
    tail = list(commands)[-limit:]
    if len(set(tail)) == 1:
        return True, tail[-1]
    return False, None


def no_progress_limit(strategy: str) -> int:  # noqa: ARG001 — unified limit; keep strategy arg for API stability
    return STAGNATION_NO_PROGRESS_STEPS


def check_stagnation(
    *,
    strategy: str,
    no_progress_streak: int,
    recent_commands: deque[str],
    repeat_limit: int = STAGNATION_REPEAT_CMD_LIMIT,
) -> tuple[bool, str, str | None]:
    """Return (should_stop, exit_reason, repeat_command)."""
    repeated, cmd = repeat_command_streak(recent_commands, limit=repeat_limit)
    if repeated:
        return True, "stagnation_repeat_command", cmd
    limit = no_progress_limit(strategy)
    if no_progress_streak >= limit:
        return True, "stagnation_no_progress", None
    return False, "", None
