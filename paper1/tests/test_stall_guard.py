from __future__ import annotations

from collections import deque
from pathlib import Path
import subprocess

from budgetflow.adapter.stall_guard import (
    check_agent_loop_stop,
    check_post_patch_stop,
    check_stagnation,
    no_progress_limit,
    normalize_bash_command,
    repeat_command_streak,
    stall_guard_enabled,
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
    assert no_progress_limit("budgetflow_segment") == STAGNATION_NO_PROGRESS_STEPS


def test_task_level_no_progress_limit_scales_with_task_effort() -> None:
    assert no_progress_limit(
        "value_aware_task_level",
        task_effort=20,
    ) == 15
    assert no_progress_limit(
        "value_aware_task_level",
        task_effort=80,
    ) == 36


def test_task_level_stagnation_uses_scaled_no_progress_limit() -> None:
    stop, reason, _ = check_stagnation(
        strategy="value_aware_task_level",
        no_progress_streak=12,
        recent_commands=deque(["grep -R x"]),
        task_effort=80,
    )
    assert stop is False
    assert reason == ""

    stop, reason, _ = check_stagnation(
        strategy="value_aware_task_level",
        no_progress_streak=36,
        recent_commands=deque(["grep -R x"]),
        task_effort=80,
    )
    assert stop is True
    assert reason == "stagnation_no_progress"


def test_task_level_stagnation_waits_for_task_budget_spend() -> None:
    stop, reason, _ = check_stagnation(
        strategy="value_aware_task_level",
        no_progress_streak=36,
        recent_commands=deque(["grep -R x"]),
        task_effort=20,
        task_spent=0.05,
        planned_task_budget=1.0,
    )
    assert stop is False
    assert reason == ""

    stop, reason, _ = check_stagnation(
        strategy="value_aware_task_level",
        no_progress_streak=36,
        recent_commands=deque(["grep -R x"]),
        task_effort=20,
        task_spent=1.0,
        planned_task_budget=1.0,
    )
    assert stop is True
    assert reason == "stagnation_no_progress"


def test_task_level_stagnation_can_stop_before_full_task_budget_when_no_progress_persists() -> None:
    stop, reason, _ = check_stagnation(
        strategy="value_aware_task_level",
        no_progress_streak=36,
        recent_commands=deque(["grep -R x"]),
        task_effort=20,
        task_spent=0.35,
        planned_task_budget=1.0,
    )

    assert stop is True
    assert reason == "stagnation_no_progress"


def test_check_stagnation_no_progress() -> None:
    stop, reason, _ = check_stagnation(
        strategy="all_pro",
        no_progress_streak=no_progress_limit("all_pro"),
        recent_commands=deque(["grep -R x"]),
    )
    assert stop is True
    assert reason == "stagnation_no_progress"


def test_post_patch_stop_only_for_verified_stable_budgetflow_patch() -> None:
    assert check_post_patch_stop(
        strategy="segment_value_aware",
        patch_digest="abc123",
        patch_stable_steps=4,
        agent_pytest="pass",
    ) == (True, "post_patch_verified_stable")

    assert check_post_patch_stop(
        strategy="segment_value_aware",
        patch_digest="abc123",
        patch_stable_steps=4,
        agent_pytest="fail",
    ) == (False, "")
    assert check_post_patch_stop(
        strategy="segment_value_aware",
        patch_digest="abc123",
        patch_stable_steps=1,
        agent_pytest="pass",
    ) == (False, "")
    assert check_post_patch_stop(
        strategy="budget_only",
        patch_digest="abc123",
        patch_stable_steps=4,
        agent_pytest="pass",
    ) == (False, "")


def test_post_patch_stop_for_stable_patch_without_submit_after_validation_runway() -> None:
    """BudgetFlow should not keep spending after a stable unsubmitted patch."""
    assert check_post_patch_stop(
        strategy="value_aware_task_level",
        patch_digest="abc123",
        patch_stable_steps=16,
        agent_pytest=None,
        agent_phase="patch_prep",
        agent_gold_edited=True,
        agent_attempted_submit=False,
        agent_submitted=False,
    ) == (True, "post_patch_stable_no_submit")

    assert check_post_patch_stop(
        strategy="value_aware_task_level",
        patch_digest="abc123",
        patch_stable_steps=16,
        agent_pytest=None,
        agent_phase="edit_gold",
        agent_gold_edited=True,
        agent_attempted_submit=False,
        agent_submitted=False,
    ) == (False, "")

    assert check_post_patch_stop(
        strategy="value_aware_task_level",
        patch_digest="abc123",
        patch_stable_steps=16,
        agent_pytest=None,
        agent_phase="patch_prep",
        agent_gold_edited=True,
        agent_attempted_submit=True,
        agent_submitted=False,
    ) == (False, "")


def test_agent_loop_stop_for_stable_patch_repeat_without_submit() -> None:
    """All strategies should stop when the agent loops on a stable patch."""
    repeated: deque[str] = deque(
        ['grep -A5 "class DecimalField" django/db/models/fields/__init__.py | head -20'] * 8,
        maxlen=16,
    )

    assert check_agent_loop_stop(
        patch_digest="abc123",
        patch_stable_steps=32,
        recent_commands=repeated,
        agent_gold_edited=True,
        agent_attempted_submit=False,
        agent_submitted=False,
    ) == (True, "agent_loop_stable_patch_no_submit", repeated[-1])


def test_agent_loop_stop_requires_stable_patch_and_no_submit() -> None:
    repeated: deque[str] = deque(["grep -R x"] * 8, maxlen=16)

    assert check_agent_loop_stop(
        patch_digest="abc123",
        patch_stable_steps=31,
        recent_commands=repeated,
        agent_gold_edited=True,
        agent_attempted_submit=False,
        agent_submitted=False,
    ) == (False, "", None)
    assert check_agent_loop_stop(
        patch_digest="abc123",
        patch_stable_steps=32,
        recent_commands=repeated,
        agent_gold_edited=True,
        agent_attempted_submit=True,
        agent_submitted=False,
    ) == (False, "", None)
    assert check_agent_loop_stop(
        patch_digest="",
        patch_stable_steps=32,
        recent_commands=repeated,
        agent_gold_edited=True,
        agent_attempted_submit=False,
        agent_submitted=False,
    ) == (False, "", None)


def test_git_diff_digest_tracks_stable_patch(tmp_path: Path) -> None:
    from budgetflow.run_trace import git_diff_digest

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    target = tmp_path / "x.py"
    target.write_text("a = 1\n")
    subprocess.run(["git", "add", "x.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    target.write_text("a = 2\n")
    first = git_diff_digest(tmp_path, changed_files=["x.py"])
    assert first
    assert git_diff_digest(tmp_path, changed_files=["x.py"]) == first

    target.write_text("a = 3\n")
    assert git_diff_digest(tmp_path, changed_files=["x.py"]) != first


# ── stall_guard_enabled gating ─────────────────────────────────────────────


def test_stall_guard_enabled_for_budgetflow_strategies() -> None:
    """BudgetFlow strategies must have stall guard enabled."""
    for strat in (
        "budgetflow_segment",
        "budgetflow_conservative",
        "segment_value_aware",
        "budgetflow_equal_weight",
        "stage_blind",
        "budgetflow_same_router",
    ):
        assert stall_guard_enabled(strat) is True, f"{strat} should have stall guard"


def test_stall_guard_disabled_for_bare_baselines() -> None:
    """Bare baselines and enterprise router must NOT have stall guard."""
    for strat in (
        "all_tier2",
        "bare_t3",
        "enterprise_router",
        "all_flash",
        "all_t1",
        "all_t3",
        "all_pro",
        "budget_only",
        "budget_only_t2",
        "workflow_level",
    ):
        assert stall_guard_enabled(strat) is False, f"{strat} should NOT have stall guard"


def test_stall_guard_disabled_for_unknown_strategy() -> None:
    assert stall_guard_enabled("") is False
    assert stall_guard_enabled("garbage") is False


def test_check_stagnation_still_works_when_enabled() -> None:
    """check_stagnation itself is unchanged — gating is at the call site."""
    stop, reason, _ = check_stagnation(
        strategy="all_tier2",
        no_progress_streak=no_progress_limit("all_tier2"),
        recent_commands=deque(["grep -R x"]),
    )
    assert stop is True
    assert reason == "stagnation_no_progress"


def test_check_stagnation_still_detects_repeat() -> None:
    cmds: deque[str] = deque(["ls"] * 6, maxlen=8)
    stop, reason, cmd = check_stagnation(
        strategy="all_tier2",
        no_progress_streak=0,
        recent_commands=cmds,
    )
    assert stop is True
    assert reason == "stagnation_repeat_command"
    assert cmd == "ls"


# ── Baseline contamination audit check ──────────────────────────────────────


def test_baseline_contamination_detected() -> None:
    from budgetflow.run_observability.audit import _baseline_contamination_check

    records = [
        {
            "exit_reason": "stagnation_repeat_command",
            "routing": "all_tier2",
            "strategy": "bare_t2_baseline",
            "harness_resolved": False,
            "exit_status": "StagnationExit",
        },
        {
            "exit_reason": "stagnation_no_progress",
            "routing": "bare_t3",
            "strategy": "bare_t3_baseline",
            "harness_resolved": False,
            "exit_status": "StagnationExit",
        },
    ]
    result = _baseline_contamination_check(records)
    assert result["contaminated"] is True
    assert result["agent_harness_stagnation_count"] == 2
    assert "bare_t2_baseline" in result["affected_strategies"]
    assert "bare_t3_baseline" in result["affected_strategies"]
    assert result["warn"]


def test_baseline_contamination_not_flagged_when_clean() -> None:
    from budgetflow.run_observability.audit import _baseline_contamination_check

    records = [
        {
            "exit_reason": "submitted",
            "routing": "all_tier2",
            "strategy": "bare_t2_baseline",
            "harness_resolved": False,
            "exit_status": "Submitted",
        },
    ]
    result = _baseline_contamination_check(records)
    assert result["contaminated"] is False
    assert result["agent_harness_stagnation_count"] == 0
    assert result["warn"] == ""


def test_baseline_contamination_ignores_budgetflow_stagnation() -> None:
    """BudgetFlow stagnation exits are NOT contamination — they're expected."""
    from budgetflow.run_observability.audit import _baseline_contamination_check

    records = [
        {
            "exit_reason": "stagnation_no_progress",
            "routing": "segment_value_aware",
            "strategy": "budgetflow_segment",
            "harness_resolved": False,
            "exit_status": "StagnationExit",
        },
    ]
    result = _baseline_contamination_check(records)
    assert result["contaminated"] is False
    assert result["agent_harness_stagnation_count"] == 0
