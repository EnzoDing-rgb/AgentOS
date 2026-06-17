"""Detect agent command loops / read-only streaks (strategy-agnostic)."""

from __future__ import annotations

from collections import deque
import math

from ..defaults import STAGNATION_NO_PROGRESS_STEPS, STAGNATION_REPEAT_CMD_LIMIT

POST_PATCH_STABLE_PASS_STEPS = 4
POST_PATCH_STABLE_NO_SUBMIT_STEPS = 16
POST_PATCH_NO_SUBMIT_PHASES = frozenset({"test", "patch_prep"})
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
# Bare baselines (all_tier2, bare_t3) and enterprise_router must NOT
# be truncated by BudgetFlow-specific stop-loss — they should exhibit
# vanilla mini-swe-agent behavior for clean evidence.
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
    planned_task_budget: float | None = None,
) -> tuple[bool, str, str | None]:
    """Return (should_stop, exit_reason, repeat_command)."""
    repeated, cmd = repeat_command_streak(recent_commands, limit=repeat_limit)
    if repeated:
        return True, "stagnation_repeat_command", cmd
    limit = no_progress_limit(strategy, task_effort=task_effort)
    if no_progress_streak >= limit:
        if (
            strategy == "value_aware_task_level"
            and planned_task_budget is not None
            and planned_task_budget > 0
            and task_spent is not None
        ):
            spent_fraction = max(0.0, float(task_spent)) / max(float(planned_task_budget), 0.000001)
            if spent_fraction < TASK_LEVEL_NO_PROGRESS_STOP_BUDGET_FRACTION:
                return False, "", None
        return True, "stagnation_no_progress", None
    return False, "", None


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
