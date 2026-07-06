"""Detect agent command loops / read-only streaks (strategy-agnostic)."""

from __future__ import annotations

from collections import deque
import math

from ..defaults import STAGNATION_NO_PROGRESS_STEPS, STAGNATION_REPEAT_CMD_LIMIT

POST_PATCH_STABLE_PASS_STEPS = 4
POST_PATCH_STABLE_NO_SUBMIT_STEPS = 16
POST_PATCH_NO_SUBMIT_PHASES = frozenset({"test", "patch_prep"})
AGENT_LOOP_STABLE_PATCH_NO_SUBMIT_STEPS = 32
AGENT_LOOP_REPEAT_CMD_LIMIT = 6
_POST_PATCH_STOP_STRATEGIES = frozenset(
    {
        "budgetflow_segment",
        "budgetflow_conservative",
        "segment_value_aware",
        "budgetflow_equal_weight",
        "stage_blind",
        "value_aware_task_level",
    }
)

# Strategies that enable the BudgetFlow stall guard (check_stagnation).
_STALL_GUARD_STRATEGIES = frozenset(
    {
        "budgetflow_segment",
        "budgetflow_conservative",
        "segment_value_aware",
        "budgetflow_equal_weight",
        "stage_blind",
        "budgetflow_same_router",
        "value_aware_task_level",
    }
)

TASK_LEVEL_NO_PROGRESS_STOP_BUDGET_FRACTION = 0.35
TASK_LEVEL_T2_NO_PROGRESS_TURN_LIMIT = 28


def stall_guard_enabled(strategy: str) -> bool:
    """Return True when the BudgetFlow stall guard should fire for *strategy*."""
    return strategy in _STALL_GUARD_STRATEGIES


def normalize_bash_command(command: str | None) -> str:
    return " ".join((command or "").split())


def repeat_command_streak(commands: deque[str], *, limit: int) -> tuple[bool, str | None]:
    if limit <= 0 or len(commands) < limit:
        return False, None
    tail = list(commands)[-limit:]
    if len(set(tail)) == 1:
        return True, tail[-1]
    return False, None


def no_progress_limit(
    strategy: str,
    *,
    task_effort: float | None = None,
) -> int:
    if strategy == "value_aware_task_level" and task_effort is not None and task_effort > 0:
        return max(STAGNATION_NO_PROGRESS_STEPS, min(36, math.ceil(task_effort * 0.75)))
    return STAGNATION_NO_PROGRESS_STEPS


def check_stagnation(
    *,
    strategy: str,
    no_progress_streak: int,
    recent_commands: deque[str],
    repeat_limit: int = STAGNATION_REPEAT_CMD_LIMIT,
    task_effort: float | None = None,
    task_spent: float | None = None,
    task_budget_cap: float | None = None,
) -> tuple[bool, str, str | None]:
    """Return (should_stop, exit_reason, repeat_command)."""
    repeated, cmd = repeat_command_streak(recent_commands, limit=repeat_limit)
    if repeated:
        return True, "stagnation_repeat_command", cmd
    limit = no_progress_limit(strategy, task_effort=task_effort)
    if no_progress_streak >= limit:
        if (
            strategy == "value_aware_task_level"
            and task_budget_cap is not None
            and task_budget_cap > 0
            and task_spent is not None
        ):
            spent_fraction = max(0.0, float(task_spent)) / max(float(task_budget_cap), 0.000001)
            if spent_fraction < TASK_LEVEL_NO_PROGRESS_STOP_BUDGET_FRACTION:
                return False, "", None
        return True, "stagnation_no_progress", None
    return False, "", None


def task_level_t2_no_progress_stop(
    *,
    strategy: str,
    backend_tier: int,
    turns_on_current_tier: int,
    no_progress_on_current_tier: int,
    agent_gold_edited: bool = False,
    patch_digest: str | None = None,
    agent_attempted_submit: bool = False,
    agent_submitted: bool = False,
    turn_limit: int = TASK_LEVEL_T2_NO_PROGRESS_TURN_LIMIT,
) -> bool:
    """Return True when task-level T2 should stop instead of burning tail budget."""
    if strategy != "value_aware_task_level":
        return False
    if int(backend_tier) != 2:
        return False
    if agent_gold_edited or patch_digest or agent_attempted_submit or agent_submitted:
        return False
    if turns_on_current_tier < turn_limit:
        return False
    return no_progress_on_current_tier >= turn_limit


def check_post_patch_stop(
    *,
    strategy: str,
    patch_digest: str | None,
    patch_stable_steps: int,
    agent_pytest: str | None,
    agent_phase: str | None = None,
    agent_gold_edited: bool = False,
    agent_attempted_submit: bool = False,
    agent_submitted: bool = False,
    stable_pass_limit: int = POST_PATCH_STABLE_PASS_STEPS,
    stable_no_submit_limit: int = POST_PATCH_STABLE_NO_SUBMIT_STEPS,
) -> tuple[bool, str]:
    """Stop BudgetFlow-only spend after a verified patch stops changing.

    This is deliberately narrower than generic post-patch stopping: failed
    validation still needs repair runway, and budget baselines remain unchanged.
    """
    if strategy not in _POST_PATCH_STOP_STRATEGIES:
        return False, ""
    if not patch_digest:
        return False, ""
    if (
        agent_gold_edited
        and not agent_attempted_submit
        and not agent_submitted
        and agent_phase in POST_PATCH_NO_SUBMIT_PHASES
        and patch_stable_steps >= stable_no_submit_limit
    ):
        return True, "post_patch_stable_no_submit"
    if agent_pytest != "pass":
        return False, ""
    if patch_stable_steps < stable_pass_limit:
        return False, ""
    return True, "post_patch_verified_stable"


def check_agent_loop_stop(
    *,
    patch_digest: str | None,
    patch_stable_steps: int,
    recent_commands: deque[str],
    agent_gold_edited: bool = False,
    agent_attempted_submit: bool = False,
    agent_submitted: bool = False,
    stable_no_submit_limit: int = AGENT_LOOP_STABLE_PATCH_NO_SUBMIT_STEPS,
    repeat_limit: int = AGENT_LOOP_REPEAT_CMD_LIMIT,
) -> tuple[bool, str, str | None]:
    """Stop strategy-agnostic agent loops after a stable patch is ignored.

    Unlike BudgetFlow stop-loss, this guard is not a routing mechanism. It
    catches vanilla agent failures where a target-file patch has stopped
    changing, the agent repeatedly inspects the same command, and no submit has
    been attempted.
    """
    if not patch_digest:
        return False, "", None
    if not agent_gold_edited:
        return False, "", None
    if agent_attempted_submit or agent_submitted:
        return False, "", None
    if patch_stable_steps < stable_no_submit_limit:
        return False, "", None
    repeated, cmd = repeat_command_streak(recent_commands, limit=repeat_limit)
    if not repeated:
        return False, "", None
    return True, "agent_loop_stable_patch_no_submit", cmd
