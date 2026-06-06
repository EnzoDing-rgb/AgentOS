from __future__ import annotations

from collections import deque

from budgetflow.adapter.stall_guard import (
    check_stagnation,
    no_progress_limit,
    normalize_bash_command,
    repeat_command_streak,
)
from budgetflow.defaults import STAGNATION_NO_PROGRESS_STEPS


def test_normalize_bash_command() -> None:
    assert normalize_bash_command("  grep   -R x  ") == "grep -R x"


def test_repeat_command_streak() -> None:
    cmds: deque[str] = deque(maxlen=8)
    for _ in range(5):
        cmds.append("grep -R foo sympy")
    ok, cmd = repeat_command_streak(cmds, limit=5)
    assert ok is True
    assert cmd == "grep -R foo sympy"


def test_no_progress_limit_unified() -> None:
    assert no_progress_limit("all_pro") == STAGNATION_NO_PROGRESS_STEPS
    assert no_progress_limit("budgetflow_full") == STAGNATION_NO_PROGRESS_STEPS


def test_check_stagnation_no_progress() -> None:
    stop, reason, _ = check_stagnation(
        strategy="all_pro",
        no_progress_streak=no_progress_limit("all_pro"),
        recent_commands=deque(["grep -R x"]),
    )
    assert stop is True
    assert reason == "stagnation_no_progress"
