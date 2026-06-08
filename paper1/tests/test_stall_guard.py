from __future__ import annotations

from collections import deque
from pathlib import Path
import subprocess

from budgetflow.adapter.stall_guard import (
    check_post_patch_stop,
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


def test_post_patch_stop_only_for_verified_stable_budgetflow_patch() -> None:
    assert check_post_patch_stop(
        strategy="budgetflow_value_aware",
        patch_digest="abc123",
        patch_stable_steps=4,
        agent_pytest="pass",
    ) == (True, "post_patch_verified_stable")

    assert check_post_patch_stop(
        strategy="budgetflow_value_aware",
        patch_digest="abc123",
        patch_stable_steps=4,
        agent_pytest="fail",
    ) == (False, "")
    assert check_post_patch_stop(
        strategy="budgetflow_value_aware",
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
