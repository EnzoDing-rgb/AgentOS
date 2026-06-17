from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.run_guards import (  # noqa: E402
    CompareRunGuards,
    GuardAction,
    _is_pipeline_failure,
    _looks_upstream,
    is_fatal_billing_error,
)


def _rec(*, resolved=False, patch=False, reason="", status=""):
    return {
        "strategy": "all_t1_baseline",
        "harness_resolved": resolved,
        "patch_extracted": patch,
        "exit_reason": reason,
        "exit_status": status,
    }


def test_pipeline_failure_detection() -> None:
    assert _is_pipeline_failure(_rec(patch=False, reason="stagnation_no_progress", status="StagnationExit"))
    assert not _is_pipeline_failure(_rec(resolved=True, patch=True, reason="submitted"))


def test_global_guard_triggers() -> None:
    g = CompareRunGuards(global_min_samples=5, global_window=10, policy_consecutive_fail=99)
    action = GuardAction()
    strategies = ["s1", "s2", "s3", "s4", "s5"]
    for name in strategies:
        r = _rec(patch=False, reason="stagnation_no_progress", status="StagnationExit")
        r["strategy"] = name
        action = g.record_task(r)
    assert action.halt_all
    assert g.is_aborted()


def test_global_guard_not_blocked_by_patches_without_resolve() -> None:
    g = CompareRunGuards(global_min_samples=5, global_window=10, policy_consecutive_fail=99)
    action = GuardAction()
    for i in range(5):
        r = _rec(resolved=False, patch=True, reason="submitted", status="Submitted")
        r["strategy"] = f"s{i}"
        action = g.record_task(r)
    assert action.halt_all
    assert g.is_aborted()


def test_policy_guard_halts_strategy_only() -> None:
    g = CompareRunGuards(policy_consecutive_fail=3, policy_pipeline_fail_min=2)
    for _ in range(3):
        action = g.record_task(_rec(patch=False, reason="stagnation_no_progress", status="StagnationExit"))
    assert action.halt_strategy == "all_t1_baseline"
    assert not action.halt_all
    assert g.is_strategy_halted("all_t1_baseline")


def test_upstream_pattern() -> None:
    assert _looks_upstream("The requested model is not supported by this provider account")
    g = CompareRunGuards(upstream_consecutive=3)
    for _ in range(3):
        action = g.record_upstream_error("503 Service temporarily unavailable", backend="tier1_spark")
    assert action.halt_all


def test_billing_errors_are_fatal() -> None:
    assert is_fatal_billing_error("Access denied, please make sure your account is in good standing")
    assert is_fatal_billing_error("overdue-payment")


def test_host_dependency_contamination_halts_all() -> None:
    g = CompareRunGuards()
    action = g.record_task(
        {
            "strategy": "budgetflow_task_level",
            "instance_id": "mwaskom__seaborn-3407",
            "detail": "host_dependency_contamination: budgetflow-runtime/worktrees/matplotlib stale path",
            "score_status": "abort",
        }
    )

    assert action.halt_all
    assert "host_dependency_contamination" in action.reason
    assert g.is_aborted()


def test_pytest_rootdir_under_runtime_worktree_does_not_halt_all() -> None:
    g = CompareRunGuards()
    action = g.record_task(
        {
            "strategy": "bare_t3_baseline",
            "instance_id": "sympy__sympy-12171",
            "detail": (
                "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; "
                "rootdir: /tmp/budgetflow-runtime/worktrees/sympy__sympy/"
                "bare_t3_baseline_sympy__sympy-12171"
            ),
            "score_status": "true_fail",
        }
    )

    assert not action.halt_all
    assert not g.is_aborted()
